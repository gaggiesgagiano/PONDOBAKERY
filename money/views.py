"""Money & accounts: the overview, cash book per account, typed money entries, paying suppliers, bank check,
VAT worksheet and the balance sheet."""
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.access import EDIT, VIEW, need
from core.models import log_change

from . import calc
from .forms import AccountForm, BankCheckForm, EntryForm
from .models import Account, Allocation, BankCheck, Entry, SupplierPayment

Z = Decimal("0")
DAY = datetime.timedelta(days=1)


def _month(request):
    try:
        y, m = (int(x) for x in request.GET.get("month", "").split("-"))
        start = datetime.date(y, m, 1)
    except (ValueError, TypeError):
        start = datetime.date.today().replace(day=1)
    nxt = (start + datetime.timedelta(days=32)).replace(day=1)
    return start, nxt - DAY, (start - DAY).replace(day=1), nxt if nxt <= datetime.date.today() else None


def _date(raw, default):
    try:
        return datetime.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return default


def _dec(raw):
    try:
        v = Decimal(str(raw).replace(",", "").replace("$", "").strip())
        return v.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


# ============================================================ overview
@need("money", VIEW)
def home(request):
    today = datetime.date.today()
    accs = list(Account.objects.all())
    if not accs:
        return render(request, "money/home.html", {"setup": True})
    bals = calc.balances(today)
    rows = []
    for a in accs:
        last = a.checks.first()
        rows.append({"a": a, "bal": bals.get(a), "last": last})
    cred = calc.creditors_by_supplier(today)
    start = calc.books_start()
    m0 = today.replace(day=1)
    vat_m = calc.vat_period(max(m0, start), today) if start <= today else None
    vat_all = calc.vat_period(start, today) if start <= today else None
    pay = calc.payroll_owed(start, today) if start <= today else None
    return render(request, "money/home.html", {
        "rows": rows, "total": sum((r["bal"] or Z for r in rows if r["a"].active), Z), "cred": cred[:8],
        "cred_total": sum((c["owing"] for c in cred), Z), "cred_overdue": sum((c["overdue"] for c in cred), Z),
        "vat_m": vat_m, "vat_owed": (vat_all["payable"] - vat_all["paid"]) if vat_all else None, "pay": pay,
        "start": start, "entries": Entry.objects.select_related("account", "to_account")[:8], "today": today})


# ============================================================ accounts
@need(owner=True)
def accounts(request):
    return render(request, "money/accounts.html", {"accounts": Account.objects.all()})


@need(owner=True)
def account_edit(request, pk=None):
    acc = get_object_or_404(Account, pk=pk) if pk else None
    if request.method == "POST":
        form = AccountForm(request.POST, instance=acc)
        if form.is_valid():
            a = form.save()
            log_change(request.user, "Money accounts", a.name, "changed" if pk else "added",
                       f"start {a.opening_date:%d %b %Y}, balance ${a.opening_balance}")
            messages.success(request, f"Saved {a.name}.")
            return redirect("money:accounts")
    else:
        form = AccountForm(instance=acc, initial=None if acc else {"opening_date": datetime.date.today()})
    return render(request, "money/account_form.html", {"form": form, "acc": acc})


@need("money", VIEW)
def book(request, pk):
    acc = get_object_or_404(Account, pk=pk)
    start, end, prev, nxt = _month(request)
    cb = calc.cash_book(acc, start, end)
    return render(request, "money/book.html", {"acc": acc, "cb": cb, "month": start, "end": end, "prev": prev, "next": nxt,
                                               "accounts": Account.objects.all(), "checks": acc.checks.all()[:6]})


@need("money", EDIT)
def bank_check(request, pk):
    acc = get_object_or_404(Account, pk=pk)
    if request.method == "POST":
        form = BankCheckForm(request.POST)
        if form.is_valid():
            bc = form.save(commit=False)
            if bc.date < acc.opening_date:
                form.add_error("date", f"{acc} starts on {acc.opening_date:%d %b %Y}.")
            else:
                bc.account, bc.checked_by = acc, request.user
                bc.pondo_balance = calc.balance(acc, bc.date)
                bc.save()
                log_change(request.user, "Money accounts", acc.name, "statement checked",
                           f"{bc.date:%d %b %Y}: statement ${bc.statement_balance}, Pondo ${bc.pondo_balance}")
                if bc.difference:
                    messages.warning(request, f"The statement differs from Pondo by ${bc.difference:,.2f}. Look for what is missing "
                                              "(bank charges, a deposit not typed, a payment typed twice) and type it, then check again.")
                else:
                    messages.success(request, "The statement and Pondo agree.")
                return redirect("money:bank_check", pk=acc.pk)
    else:
        form = BankCheckForm(initial={"date": datetime.date.today()})
    return render(request, "money/bank_check.html", {"acc": acc, "form": form, "checks": acc.checks.select_related("checked_by")})


# ============================================================ typed money entries
@need("money", EDIT)
def entry_edit(request, pk=None):
    en = get_object_or_404(Entry, pk=pk) if pk else None
    if not Account.objects.exists():
        messages.error(request, "First set up the money accounts (safe, bank, EcoCash).")
        return redirect("money:home")
    if request.method == "POST":
        form = EntryForm(request.POST, instance=en)
        if form.is_valid():
            e = form.save(commit=False)
            if not pk:
                e.created_by = request.user
            e.to_account = form.cleaned_data.get("to_account")
            e.save()
            log_change(request.user, "Money entries", f"{e.date:%d %b %Y} {e.get_kind_display()}", "changed" if pk else "added",
                       f"${e.amount} {e.account}{' → ' + str(e.to_account) if e.to_account else ''} {e.description}")
            messages.success(request, "Saved.")
            return redirect(f"/money/accounts/{e.account_id}/?month={e.date:%Y-%m}")
    else:
        init = {}
        if not en:
            if request.GET.get("kind"):
                init["kind"] = request.GET["kind"]
            if request.GET.get("account"):
                init["account"] = request.GET["account"]
        form = EntryForm(instance=en, initial=init)
    return render(request, "money/entry_form.html", {"form": form, "en": en, "in_kinds": sorted(Entry.IN_KINDS)})


@need("money", EDIT)
@require_POST
def entry_delete(request, pk):
    en = get_object_or_404(Entry, pk=pk)
    log_change(request.user, "Money entries", f"{en.date:%d %b %Y} {en.get_kind_display()}", "deleted", f"${en.amount} {en.account}")
    acc, d = en.account_id, en.date
    en.delete()
    messages.success(request, "Deleted.")
    return redirect(f"/money/accounts/{acc}/?month={d:%Y-%m}")


# ============================================================ suppliers we owe
@need("money", VIEW)
def creditors_view(request):
    as_at = _date(request.GET.get("date"), datetime.date.today())
    rows = calc.creditors(as_at)
    per = calc.creditors_by_supplier(as_at)
    return render(request, "money/creditors.html", {"rows": rows, "per": per, "as_at": as_at,
                                                    "total": sum((r["owing"] for r in rows), Z),
                                                    "overdue": sum((r["owing"] for r in rows if r["late"]), Z),
                                                    "payments": SupplierPayment.objects.select_related("supplier", "account")[:15]})


@need("money", VIEW)
def statement(request, pk):
    from costing.models import Supplier
    sup = get_object_or_404(Supplier, pk=pk)
    today = datetime.date.today()
    start = _date(request.GET.get("from"), (today - datetime.timedelta(days=90)).replace(day=1))
    end = _date(request.GET.get("to"), today)
    st = calc.supplier_statement(sup, start, end)
    return render(request, "money/statement.html", {"sup": sup, "st": st, "start": start, "end": end,
                                                    "open": calc.creditors(calc.FAR, sup)})


@need("money", EDIT)
def pay(request):
    from costing.models import Supplier
    if not Account.objects.exists():
        messages.error(request, "First set up the money accounts (safe, bank, EcoCash).")
        return redirect("money:home")
    sups = Supplier.objects.filter(active=True)
    sup = Supplier.objects.filter(pk=request.POST.get("supplier") or request.GET.get("supplier") or 0).first()
    open_rows = calc.creditors(calc.FAR, sup) if sup else []
    error = None
    post = request.POST if request.method == "POST" else {}
    for r in open_rows:
        r["val"] = post.get(f"grv_{r['grv'].pk}", "") if post else ""
    if request.method == "POST" and sup:
        d = _date(request.POST.get("date"), None)
        amount = _dec(request.POST.get("amount"))
        acc_raw = request.POST.get("account")
        acc = Account.objects.filter(pk=acc_raw).first() if acc_raw and acc_raw != "owner" else None
        allocs, total = [], Z
        for r in open_rows:
            v = _dec(request.POST.get(f"grv_{r['grv'].pk}")) if request.POST.get(f"grv_{r['grv'].pk}") else None
            if v:
                if v < 0 or v > r["owing"]:
                    error = f"{r['grv'].number}: you can pay at most ${r['owing']:,.2f}."
                allocs.append((r["grv"], v))
                total += v
        if d is None:
            error = "Type the date paid."
        elif amount is None or amount <= 0:
            error = "Type the amount paid."
        elif acc_raw not in ("owner",) and acc is None:
            error = "Choose the account the money was paid from."
        elif acc and d < acc.opening_date:
            error = f"{acc} starts on {acc.opening_date:%d %b %Y} – the date can't be before that."
        elif not allocs:
            error = "Type how much of each invoice this payment pays (or press 'Fill oldest first')."
        elif total != amount and not error:
            error = f"The invoices add up to ${total:,.2f} but the payment is ${amount:,.2f} – they must be the same."
        if not error:
            with transaction.atomic():
                p = SupplierPayment.objects.create(supplier=sup, date=d, account=acc, amount=amount,
                                                   ref=(request.POST.get("ref") or "")[:60], notes=(request.POST.get("notes") or "")[:200],
                                                   created_by=request.user)
                for g, v in allocs:
                    Allocation.objects.create(payment=p, grv=g, amount=v)
            log_change(request.user, "Supplier payments", p.number, "paid",
                       f"{sup} ${amount} from {acc or 'owner'} – " + ", ".join(f"{g.number} ${v}" for g, v in allocs))
            messages.success(request, f"Payment {p.number} saved – ${amount:,.2f} to {sup}.")
            return redirect("money:payment", pk=p.pk)
    return render(request, "money/pay.html", {"sups": sups, "sup": sup, "open": open_rows, "error": error, "post": post,
                                              "accounts": Account.objects.filter(active=True), "today": datetime.date.today(),
                                              "owing": sum((r["owing"] for r in open_rows), Z)})


@need("money", VIEW)
def payment(request, pk):
    p = get_object_or_404(SupplierPayment.objects.select_related("supplier", "account", "created_by"), pk=pk)
    return render(request, "money/payment.html", {"p": p, "allocs": p.allocations.select_related("grv")})


@need(owner=True)
@require_POST
def payment_delete(request, pk):
    p = get_object_or_404(SupplierPayment, pk=pk)
    log_change(request.user, "Supplier payments", p.number, "deleted", f"{p.supplier} ${p.amount}")
    sup = p.supplier_id
    p.delete()
    messages.success(request, "Payment deleted – those invoices show as unpaid again.")
    return redirect("money:statement", pk=sup)


# ============================================================ VAT
@need("money", VIEW)
def vat(request):
    from core.models import CompanySettings
    start, end, prev, nxt = _month(request)
    v = calc.vat_period(start, end)
    bs = calc.books_start()
    owed = None
    if bs and bs <= end:
        allv = calc.vat_period(bs, end)
        owed = allv["payable"] - allv["paid"]
    return render(request, "money/vat.html", {"v": v, "month": start, "prev": prev, "next": nxt, "owed": owed, "bs": bs,
                                              "cs": CompanySettings.get(),
                                              "payments": Entry.objects.filter(kind=Entry.VAT, date__gte=start, date__lte=end)})


# ============================================================ balance sheet
@need("money", VIEW)
def balance_sheet_view(request):
    as_at = _date(request.GET.get("date"), datetime.date.today())
    bs = calc.balance_sheet(as_at)
    return render(request, "money/balance.html", {"bs": bs, "as_at": as_at, "print": request.GET.get("print")})
