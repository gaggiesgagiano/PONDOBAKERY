"""The sums behind Money & accounts: cash book per account, what we owe suppliers, VAT and the balance sheet.

Most money movements are not typed twice: they are read from where they were already recorded (cash-ups,
expenses, payroll, advances, paid invoices). Only what Pondo cannot know is typed as an Entry.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from .models import Account, Allocation, BankCheck, Entry, SupplierPayment

Z = Decimal("0")
C = Decimal("0.01")
DAY = datetime.timedelta(days=1)
FAR = datetime.date(2999, 12, 31)   # "everything, also future-dated"


def r2(v):
    return (v or Z).quantize(C)


# ============================================================ accounts
def default_account(kind):
    return Account.objects.filter(kind=kind, active=True).order_by("sort_order", "pk").first() or \
        Account.objects.filter(kind=kind).order_by("sort_order", "pk").first()


def books_start():
    """The first day of the books (the earliest account start date)."""
    a = Account.objects.order_by("opening_date").first()
    return a.opening_date if a else None


def _method_account(method, cache):
    if method.pk not in cache:
        acc = getattr(method, "account", None)
        if acc is None:
            low = method.name.lower()
            kind = Account.SAFE if method.is_cash else (Account.MOBILE if ("eco" in low or "mobile" in low) else Account.BANK)
            acc = default_account(kind)
        cache[method.pk] = acc
    return cache[method.pk]


def _paid_how_account(how):
    low = (how or "").lower()
    if "eco" in low or "mobile" in low:
        return default_account(Account.MOBILE)
    if "cash" in low:
        return default_account(Account.SAFE)
    return default_account(Account.BANK)


def all_flows(start, end):
    """Every money movement from start to end (both days included), per account id.
    Each row: date, what, ref, url, amount (+ in / − out), source."""
    from django.urls import reverse

    from invoices.models import Document
    from sales.models import CashUp, Expense
    from staff.models import Advance, PayRun

    out = defaultdict(list)

    def add(acc, d, what, amount, ref="", url="", source=""):
        if acc is None or not amount:
            return
        out[acc.pk].append({"date": d, "what": what, "amount": r2(amount), "ref": ref, "url": url, "source": source})

    safe = default_account(Account.SAFE)
    mcache = {}
    # ---- cash-ups: drawer cash goes back to the safe (the float came from the safe); other payments to their account
    for cu in CashUp.objects.filter(date__gte=start, date__lte=end).prefetch_related("lines__method"):
        url = reverse("sales:cashup", args=[cu.pk])
        if cu.cash_counted is not None:
            cash = cu.cash_counted + (cu.drops or Z) + (cu.zig_usd or Z) - (cu.opening_float or Z)
            add(safe, cu.date, f"Cash-up {cu.till} – cash to the safe", cash, cu.number, url, "cashup")
        for ln in cu.lines.all():
            if ln.method.is_cash:
                continue
            amt = ln.actual_amount if ln.actual_amount is not None else ln.till_amount
            add(_method_account(ln.method, mcache), cu.date, f"Cash-up {cu.till} – {ln.method.name}", amt, cu.number, url, "cashup")
    # ---- expenses paid from the bank / EcoCash (till pay-outs are already inside the cash-up)
    bank = default_account(Account.BANK)
    for e in Expense.objects.filter(date__gte=start, date__lte=end, paid_from=Expense.BANK, cashup__isnull=True).select_related("category"):
        acc = getattr(e, "account", None) or bank
        add(acc, e.date, f"Expense – {e.category}{' · ' + e.payee if e.payee else ''}", -e.amount, e.receipt_no,
            reverse("sales:expense_edit", args=[e.pk]), "expense")
    # ---- supplier payments
    for p in SupplierPayment.objects.filter(date__gte=start, date__lte=end, account__isnull=False).select_related("supplier", "account"):
        add(p.account, p.date, f"Paid supplier – {p.supplier}", -p.amount, p.ref or p.number,
            reverse("money:payment", args=[p.pk]), "supplier")
    # ---- typed entries
    for en in Entry.objects.filter(date__gte=start, date__lte=end).select_related("account", "to_account"):
        url = reverse("money:entry_edit", args=[en.pk])
        what = en.get_kind_display() + (f" – {en.description}" if en.description else "")
        if en.kind == Entry.TRANSFER:
            add(en.account, en.date, f"Moved to {en.to_account}" + (f" – {en.description}" if en.description else ""), -en.amount, en.ref, url, "entry")
            add(en.to_account, en.date, f"Moved from {en.account}" + (f" – {en.description}" if en.description else ""), en.amount, en.ref, url, "entry")
        else:
            add(en.account, en.date, what, en.amount if en.is_in else -en.amount, en.ref, url, "entry")
    # ---- wages (final pay runs), per way of paying
    kind_of = {"cash": Account.SAFE, "bank": Account.BANK, "ecocash": Account.MOBILE}
    for run in PayRun.objects.filter(status=PayRun.FINAL, pay_date__gte=start, pay_date__lte=end).prefetch_related("lines__employee"):
        per = defaultdict(lambda: Z)
        for ln in run.lines.all():
            per[kind_of.get(ln.employee.paid_by, Account.BANK)] += ln.net
        for k, amt in per.items():
            add(default_account(k), run.pay_date, f"Wages {run.period:%B %Y}", -amt, run.number,
                reverse("staff:payrun", args=[run.pk]), "wages")
    # ---- staff advances (cash from the safe)
    for a in Advance.objects.filter(date__gte=start, date__lte=end).select_related("employee"):
        add(safe, a.date, f"Staff advance – {a.employee.name}", -a.amount, "", "", "advance")
    # ---- customer invoices that were paid
    from invoices.models import Delivery
    on_till = set(Delivery.objects.values_list("doc_id", flat=True))   # delivery money comes in through the till / cash-up
    for d in Document.objects.filter(kind=Document.INVOICE, status=Document.PAID, paid_on__gte=start, paid_on__lte=end).exclude(pk__in=on_till):
        add(_paid_how_account(d.paid_how), d.paid_on, f"Invoice paid – {d.company or d.name}", d.total, d.number,
            reverse("invoices:doc", args=[d.pk]), "invoice")
    return out


_URLS = {}


def _has_url(name):
    if name not in _URLS:
        from django.urls import NoReverseMatch, reverse
        try:
            reverse(name, args=[1])
            _URLS[name] = True
        except NoReverseMatch:
            _URLS[name] = False
    return _URLS[name]


def balance(acc, as_at, flows=None):
    if as_at < acc.opening_date:
        return None
    rows = flows if flows is not None else all_flows(acc.opening_date, as_at).get(acc.pk, [])
    return acc.opening_balance + sum((r["amount"] for r in rows if acc.opening_date <= r["date"] <= as_at), Z)


def balances(as_at):
    """{account: balance} for all accounts on a day (None when the account starts later)."""
    accs = list(Account.objects.all())
    if not accs:
        return {}
    start = min(a.opening_date for a in accs)
    flows = all_flows(start, as_at) if start <= as_at else {}
    return {a: balance(a, as_at, flows.get(a.pk, [])) for a in accs}


def cash_book(acc, start, end):
    """Rows for one account from start to end, with the running balance."""
    s = max(start, acc.opening_date)
    opening = balance(acc, s - DAY) if s > acc.opening_date else acc.opening_balance
    if end < acc.opening_date:
        return {"opening": None, "rows": [], "closing": None, "in": Z, "out": Z}
    rows = sorted(all_flows(s, end).get(acc.pk, []), key=lambda r: (r["date"], r["amount"] < 0))
    run = opening
    for r in rows:
        run += r["amount"]
        r["balance"] = run
    return {"opening": opening, "rows": rows, "closing": run, "start": s,
            "in": sum((r["amount"] for r in rows if r["amount"] > 0), Z),
            "out": -sum((r["amount"] for r in rows if r["amount"] < 0), Z)}


# ============================================================ suppliers (creditors)
def grv_amount(g):
    return g.invoice_total if g.invoice_total is not None else r2(g.total)


def creditors(as_at=None, supplier=None):
    """Supplier invoices (GRVs) not fully paid on a day: amount, paid, owing, due date and days late."""
    from stock.models import GRV
    as_at = as_at or datetime.date.today()
    qs = GRV.objects.filter(date__lte=as_at).select_related("supplier").prefetch_related("lines__ingredient")
    if supplier:
        qs = qs.filter(supplier=supplier)
    start = books_start()
    if start:
        qs = qs.filter(date__gte=start)
    paid = defaultdict(lambda: Z)
    for a in Allocation.objects.filter(payment__date__lte=as_at).values("grv_id", "amount"):
        paid[a["grv_id"]] += a["amount"]
    rows = []
    for g in qs.order_by("date", "pk"):
        amt = grv_amount(g)
        owing = amt - paid[g.pk]
        if owing <= Z:
            continue
        terms = g.supplier.terms_days or 0
        due = g.date + datetime.timedelta(days=terms)
        rows.append({"grv": g, "supplier": g.supplier, "amount": amt, "paid": paid[g.pk], "owing": owing, "due": due,
                     "late": max((min(as_at, datetime.date.today()) - due).days, 0)})
    return rows


def creditors_by_supplier(as_at=None):
    per = {}
    for r in creditors(as_at):
        s = per.setdefault(r["supplier"].pk, {"supplier": r["supplier"], "owing": Z, "overdue": Z, "n": 0, "oldest": r["grv"].date,
                                             "b0": Z, "b30": Z, "b60": Z, "b90": Z})
        s["owing"] += r["owing"]
        s["n"] += 1
        if r["late"] > 0:
            s["overdue"] += r["owing"]
        age = r["late"]
        s["b0" if age == 0 else "b30" if age <= 30 else "b60" if age <= 60 else "b90"] += r["owing"]
    return sorted(per.values(), key=lambda s: -s["owing"])


def supplier_statement(supplier, start, end):
    """Invoices (GRVs) and payments for one supplier, with the running amount we owe."""
    from stock.models import GRV
    bs = books_start() or start
    opening_rows = creditors(start - DAY, supplier) if start > bs else []
    opening = sum((r["owing"] for r in opening_rows), Z)
    rows = []
    for g in GRV.objects.filter(supplier=supplier, date__gte=max(start, bs), date__lte=end).prefetch_related("lines__ingredient"):
        rows.append({"date": g.date, "what": f"Invoice {g.invoice_no or '–'} ({g.number})", "debit": grv_amount(g), "credit": Z, "obj": g, "kind": "grv"})
    for p in SupplierPayment.objects.filter(supplier=supplier, date__gte=start, date__lte=end).select_related("account"):
        rows.append({"date": p.date, "what": f"Payment {p.number} – {p.account or 'owner paid'}{' · ' + p.ref if p.ref else ''}",
                     "debit": Z, "credit": p.amount, "obj": p, "kind": "pay"})
    rows.sort(key=lambda r: (r["date"], r["kind"] == "pay"))
    run = opening
    for r in rows:
        run += r["debit"] - r["credit"]
        r["balance"] = run
    return {"opening": opening, "rows": rows, "closing": run}


# ============================================================ VAT
def vat_period(start, end):
    """VAT on sales (output) minus VAT on purchases and expenses (input), from start to end."""
    from invoices.models import Document
    from sales.models import CashUp, DailySales, Expense
    from stock.models import GRV
    from till.models import Sale

    till = defaultdict(lambda: Z)
    for s in Sale.objects.filter(shift__date__gte=start, shift__date__lte=end).values("shift__date", "vat"):
        till[s["shift__date"]] += s["vat"]
    daily = {d.date: d.total for d in DailySales.objects.filter(date__gte=start, date__lte=end)}
    cu = defaultdict(lambda: Z)
    for c in CashUp.objects.filter(date__gte=start, date__lte=end):
        cu[c.date] += c.total_sales
    typed_vat, missing = Z, []
    for d, excl in daily.items():
        if d in till:
            continue
        if d in cu:
            typed_vat += cu[d] - excl     # takings incl. VAT minus sales excl. VAT
        else:
            missing.append(d)
    till_vat = sum(till.values(), Z)
    from invoices.models import Delivery
    inv = list(Document.objects.filter(kind=Document.INVOICE, date__gte=start, date__lte=end).exclude(status=Document.CANCELLED)
               .exclude(pk__in=Delivery.objects.values_list("doc_id", flat=True)))   # delivery invoices are on the till already
    inv_vat = sum((d.vat for d in inv), Z)
    output = till_vat + typed_vat + inv_vat

    grvs = list(GRV.objects.filter(date__gte=start, date__lte=end).prefetch_related("lines__ingredient"))
    grv_vat = sum((g.total - g.total_excl for g in grvs), Z)
    exps = list(Expense.objects.filter(date__gte=start, date__lte=end))
    exp_vat = sum((e.vat or Z for e in exps), Z)
    inp = grv_vat + exp_vat
    paid = sum((e.amount for e in Entry.objects.filter(kind=Entry.VAT, date__gte=start, date__lte=end)), Z)
    return {"start": start, "end": end, "till_vat": r2(till_vat), "typed_vat": r2(typed_vat), "inv_vat": r2(inv_vat),
            "n_inv": len(inv), "output": r2(output), "grv_vat": r2(grv_vat), "n_grv": len(grvs), "exp_vat": r2(exp_vat),
            "n_exp": sum(1 for e in exps if e.vat), "input": r2(inp), "payable": r2(output - inp), "paid": r2(paid),
            "missing": sorted(missing)}


# ============================================================ PAYE / NSSA / ZIMDEF owed
def payroll_owed(start, as_at):
    from staff.models import PayRun
    due = {"paye": Z, "nssa": Z, "zimdef": Z}
    for run in PayRun.objects.filter(status=PayRun.FINAL, pay_date__gte=start, pay_date__lte=as_at).prefetch_related("lines"):
        for ln in run.lines.all():
            due["paye"] += ln.paye + ln.aids_levy
            due["nssa"] += ln.nssa + ln.nssa_employer
            due["zimdef"] += ln.zimdef
    paid = {k: sum((e.amount for e in Entry.objects.filter(kind=k, date__gte=start, date__lte=as_at)), Z) for k in due}
    return {k: {"due": r2(due[k]), "paid": r2(paid[k]), "owed": r2(due[k] - paid[k])} for k in due}


# ============================================================ balance sheet
def balance_sheet(as_at):
    from equipment.models import Item
    from invoices.models import Document
    from sales.models import Expense
    from staff.models import Advance
    from stock.models import StockCount

    start = books_start()
    if start is None or as_at < start:
        return None
    bals = balances(as_at)
    money = [(a, b) for a, b in bals.items() if b is not None]
    cash_total = sum((b for _, b in money), Z)

    count = StockCount.objects.filter(status=StockCount.FINAL, date__lte=as_at).order_by("-date", "-pk").first()
    stock = count.total_value if count and count.total_value is not None else Z
    debtors_list = [d for d in Document.objects.filter(kind=Document.INVOICE, date__lte=as_at).exclude(status=Document.CANCELLED)
                    if not (d.status == Document.PAID and d.paid_on and d.paid_on <= as_at)]
    debtors = sum((d.total for d in debtors_list), Z)
    advances = sum((a.amount for a in Advance.objects.filter(date__lte=as_at)
                    .filter(models_q_not_recovered(as_at))), Z)
    month = as_at.replace(day=1)
    items = list(Item.objects.select_related("category"))
    equip = sum((i.book_value(month) for i in items if i.purchase_date <= as_at), Z)
    # what was already there when the books started: put in by the owner / boss
    before = (start.replace(day=1) - DAY).replace(day=1)
    open_equip = sum((i.book_value(before) for i in items if i.purchase_date < start), Z)
    open_count = StockCount.objects.filter(status=StockCount.FINAL, date__lte=start).order_by("-date", "-pk").first()
    open_stock = open_count.total_value if open_count and open_count.total_value is not None else Z
    open_money = sum((a.opening_balance for a in Account.objects.all()), Z)
    opening = open_money + open_equip + open_stock

    cred = sum((r["owing"] for r in creditors(as_at)), Z)
    vat = vat_period(start, as_at)
    vat_owed = vat["payable"] - vat["paid"]
    pay = payroll_owed(start, as_at)
    E = Entry.objects.filter(date__gte=start, date__lte=as_at)
    tot = lambda k: sum((e.amount for e in E.filter(kind=k)), Z)  # noqa: E731
    loans = tot(Entry.LOAN_IN) - tot(Entry.LOAN_REPAY)
    owner_paid = (sum((e.amount for e in Expense.objects.filter(paid_from=Expense.OWNER, date__gte=start, date__lte=as_at)), Z)
                  + sum((p.amount for p in SupplierPayment.objects.filter(account__isnull=True, date__gte=start, date__lte=as_at)), Z))
    capital = tot(Entry.OWNER_IN)
    drawings = tot(Entry.DRAWINGS)

    assets = [("Money in the accounts", cash_total), ("Stock (last final stock take" + (f", {count.date:%d %b %Y})" if count else " – none yet)"), stock),
              ("Customers owe us (unpaid invoices)", debtors), ("Staff owe us (advances not yet taken off pay)", advances),
              ("Equipment (book value)", equip)]
    if vat_owed < 0:
        assets.append(("VAT ZIMRA owes us", -vat_owed))
    liabilities = [("We owe suppliers", cred), ("PAYE & AIDS levy not yet paid to ZIMRA", pay["paye"]["owed"]),
                   ("NSSA not yet paid", pay["nssa"]["owed"]), ("ZIMDEF not yet paid", pay["zimdef"]["owed"]),
                   ("Loans to the business", loans), ("Owed to the owner / boss (paid from own pocket)", owner_paid)]
    if vat_owed > 0:
        liabilities.insert(1, ("VAT we owe ZIMRA", vat_owed))
    total_assets = sum((v for _, v in assets), Z)
    total_liab = sum((v for _, v in liabilities), Z)
    net = total_assets - total_liab
    kept = net - opening - capital + drawings
    return {"as_at": as_at, "start": start, "money": money, "assets": assets, "liabilities": liabilities,
            "total_assets": r2(total_assets), "total_liab": r2(total_liab), "net": r2(net), "capital": r2(capital),
            "drawings": r2(drawings), "kept": r2(kept), "opening": r2(opening),
            "open_parts": {"money": r2(open_money), "equip": r2(open_equip), "stock": r2(open_stock)}, "stock_count": count, "debtors_list": debtors_list,
            "vat": vat, "pay": pay}


def models_q_not_recovered(as_at):
    """Advances still owed on a day: not yet taken off a final pay run paid on or before that day."""
    from django.db.models import Q
    return Q(recovered_in__isnull=True) | Q(recovered_in__run__pay_date__gt=as_at) | ~Q(recovered_in__run__status="final")


# ============================================================ for the accountant's month pack
def pack_extra(start, end):
    """Cash book per account, suppliers owed and the balance sheet at the month end (None until accounts are set up)."""
    accs = list(Account.objects.all())
    if not accs:
        return None
    books = []
    for a in accs:
        if end < a.opening_date:
            continue
        cb = cash_book(a, start, end)
        last = a.checks.filter(date__lte=end).first()
        books.append({"a": a, "cb": cb, "check": last})
    cred = creditors(end)
    return {"books": books, "cred": cred, "cred_total": sum((r["owing"] for r in cred), Z),
            "payments": list(SupplierPayment.objects.filter(date__gte=start, date__lte=end).select_related("supplier", "account")),
            "bs": balance_sheet(end)}
