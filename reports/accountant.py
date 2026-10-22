"""The accountant's month pack: everything for one month, 1st to last day, in one place.

Uses the same figures as the Month-end report (reports/calc.py) and adds the full lists behind them:
sales per day, takings, every expense, every supplier invoice (GRV), payroll and statutory payments,
invoices issued and unpaid, deliveries, stock and cost of sales, equipment – and a list of things to check.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q

from core.models import CompanySettings

from .calc import month_bounds, month_end

Z = Decimal("0")
C = Decimal("0.01")


def r2(v):
    return (v or Z).quantize(C)


def accountant_pack(month, with_payroll=True):
    from equipment.models import Item
    from invoices.models import Delivery, Document
    from sales.models import CashUp, DailySales, DailySalesLine, Expense
    from staff.models import PayLine, PayRun
    from stock.models import GRV

    start, nxt = month_bounds(month)
    end = nxt - datetime.timedelta(days=1)
    m = month_end(start)
    cs = CompanySettings.get()
    checks = []

    # ------------------------------------------------------------------ sales & takings per day
    ds = {d.date: d for d in DailySales.objects.filter(date__gte=start, date__lt=nxt)}
    cus_by_day = defaultdict(list)
    for c in CashUp.objects.filter(date__gte=start, date__lt=nxt).prefetch_related("lines__method", "expenses"):
        cus_by_day[c.date].append(c)
    days = []
    d = start
    while d <= end:
        sale = ds.get(d)
        cus = cus_by_day.get(d, [])
        till = sum((c.total_sales for c in cus), Z)
        row = {"date": d, "sales": sale.total if sale else None, "till": till if cus else None,
               "vat": (till - sale.total) if (sale and cus) else None,
               "variance": sum((c.total_variance for c in cus), Z) if cus else None,
               "payouts": sum((sum((e.amount for e in c.expenses.all()), Z) for c in cus), Z) if cus else None,
               "banked": sum((c.banked or Z for c in cus), Z) if cus else None,
               "zig": sum((c.zig_counted or Z for c in cus), Z) if cus else None,
               "n_tills": len(cus), "unsigned": sum(1 for c in cus if not c.signed_off_at)}
        days.append(row)
        d += datetime.timedelta(days=1)
    tot_days = {k: sum((r[k] or Z for r in days), Z) for k in ("sales", "till", "vat", "variance", "payouts", "banked", "zig")}
    no_sales = [r["date"] for r in days if r["sales"] is None and r["till"] is not None]
    no_cashup = [r["date"] for r in days if r["till"] is None and r["sales"] is not None]
    unsigned = sum(r["unsigned"] for r in days)
    if no_sales:
        checks.append(f"{len(no_sales)} day(s) with a cash-up but no daily sales typed: "
                      + ", ".join(f"{x:%d %b}" for x in no_sales[:8]) + ("…" if len(no_sales) > 8 else ""))
    if no_cashup:
        checks.append(f"{len(no_cashup)} day(s) with daily sales but no cash-up: "
                      + ", ".join(f"{x:%d %b}" for x in no_cashup[:8]) + ("…" if len(no_cashup) > 8 else ""))
    if unsigned:
        checks.append(f"{unsigned} cash-up(s) not signed off by a manager.")
    if not ds:
        checks.append("No daily sales typed for this month.")

    cat = defaultdict(lambda: Z)
    for ln in DailySalesLine.objects.filter(day__date__gte=start, day__date__lt=nxt).select_related("category"):
        cat[ln.category.name] += ln.amount
    by_category = sorted(cat.items(), key=lambda x: -x[1])

    methods = [(x["method__name"], x["t"] or Z) for x in m["methods"]]

    # ------------------------------------------------------------------ expenses
    exps = list(Expense.objects.filter(date__gte=start, date__lt=nxt).select_related("category").order_by("date", "id"))
    exp_rows = [{"e": e, "excl": e.amount_excl, "vat": e.vat or Z, "incl": e.amount} for e in exps]
    exp_tot = {"excl": sum((r["excl"] for r in exp_rows), Z), "vat": sum((r["vat"] for r in exp_rows), Z),
               "incl": sum((r["incl"] for r in exp_rows), Z)}
    by_paid = defaultdict(lambda: Z)
    for e in exps:
        by_paid[e.get_paid_from_display()] += e.amount
    owner_paid = sum((e.amount for e in exps if e.paid_from == Expense.OWNER), Z)
    if owner_paid:
        checks.append(f"${owner_paid:,.2f} of expenses were paid by the owner personally – owner's loan / drawings account.")
    no_receipt = sum(1 for e in exps if not e.receipt_no.strip())
    if no_receipt:
        checks.append(f"{no_receipt} expense(s) without a receipt / slip number.")

    # ------------------------------------------------------------------ purchases (GRVs)
    grvs = list(GRV.objects.filter(date__gte=start, date__lt=nxt).select_related("supplier")
                .prefetch_related("lines__ingredient").order_by("date", "id"))
    grv_rows = []
    for g in grvs:
        lines = list(g.lines.all())
        incl = sum((ln.line_total for ln in lines), Z)
        excl = sum((ln.value_excl for ln in lines), Z)
        diff = (g.invoice_total - incl) if g.invoice_total is not None else None
        grv_rows.append({"g": g, "excl": excl, "vat": incl - excl, "incl": incl, "invoice_total": g.invoice_total,
                         "diff": diff, "bad": diff is not None and abs(diff) >= Decimal("0.05")})
    grv_tot = {k: sum((r[k] for r in grv_rows), Z) for k in ("excl", "vat", "incl")}
    sup = defaultdict(lambda: [Z, Z, Z, 0])
    for r in grv_rows:
        s = sup[r["g"].supplier.name]
        s[0] += r["excl"]; s[1] += r["vat"]; s[2] += r["incl"]; s[3] += 1  # noqa: E702
    by_supplier = sorted(((k, *v) for k, v in sup.items()), key=lambda x: -x[1])
    mism = [r for r in grv_rows if r["bad"]]
    if mism:
        checks.append(f"{len(mism)} supplier invoice(s) where the invoice total differs from the goods received "
                      f"(see Purchases).")
    no_inv = sum(1 for r in grv_rows if not r["g"].invoice_no.strip())
    if no_inv:
        checks.append(f"{no_inv} delivery(ies) from suppliers without a supplier invoice number.")

    # ------------------------------------------------------------------ payroll
    runs = list(PayRun.objects.filter(period__gte=start, period__lt=nxt))
    pay = None
    if with_payroll:
        lines = list(PayLine.objects.filter(run__in=[r for r in runs if r.status != PayRun.DRAFT])
                     .select_related("employee", "run").order_by("employee__code"))
        keys = ["basic", "overtime_pay", "allowances", "bonus", "other_earnings", "gross", "nssa", "paye",
                "aids_levy", "advances", "other_deductions", "net", "nssa_employer", "zimdef"]
        t = {k: sum((getattr(ln, k) for ln in lines), Z) for k in keys}
        t["cost"] = t["gross"] + t["nssa_employer"] + t["zimdef"]
        t["extra"] = t["allowances"] + t["bonus"] + t["other_earnings"]
        t["deduct"] = t["advances"] + t["other_deductions"]
        for ln in lines:
            ln.extra = ln.allowances + ln.bonus + ln.other_earnings
            ln.deduct = ln.advances + ln.other_deductions
        pay = {"lines": lines, "t": t, "runs": runs,
               "zimra": t["paye"] + t["aids_levy"], "nssa_total": t["nssa"] + t["nssa_employer"]}
    if not runs:
        checks.append("No pay run for this month – wages in the income statement are the monthly salary list, "
                      "not the actual payroll.")
    elif any(r.status == PayRun.DRAFT for r in runs):
        checks.append("The pay run for this month is still a draft – it is left out of the payroll figures.")

    # ------------------------------------------------------------------ invoices & debtors
    inv = list(Document.objects.filter(kind=Document.INVOICE, date__gte=start, date__lt=nxt)
               .exclude(status=Document.CANCELLED).order_by("seq"))
    cancelled = Document.objects.filter(kind=Document.INVOICE, date__gte=start, date__lt=nxt,
                                        status=Document.CANCELLED).count()
    deliv_doc_ids = set(Delivery.objects.filter(doc__in=inv).values_list("doc_id", flat=True))
    inv_rows = [{"d": x, "delivery": x.pk in deliv_doc_ids} for x in inv]
    inv_tot = {k: sum((getattr(x, k) for x in inv), Z) for k in ("subtotal", "vat", "total")}
    inv_other = [r["d"] for r in inv_rows if not r["delivery"]]
    inv_other_tot = {k: sum((getattr(x, k) for x in inv_other), Z) for k in ("subtotal", "vat", "total")}
    debtors = list(Document.objects.filter(kind=Document.INVOICE, date__lte=end)
                   .exclude(status=Document.CANCELLED)
                   .filter(Q(status=Document.OPEN) | Q(status=Document.ACCEPTED) | Q(paid_on__gt=end))
                   .order_by("date"))
    deb_rows = [{"d": x, "days": (end - x.date).days} for x in debtors]
    deb_tot = sum((x.total for x in debtors), Z)
    if inv_other:
        checks.append(f"{len(inv_other)} tax invoice(s) not linked to a delivery (${inv_other_tot['total']:,.2f}) – "
                      "check whether they were also rung up on the till, so they are not counted twice or missed.")

    # ------------------------------------------------------------------ deliveries
    dels = list(Delivery.objects.filter(date__gte=start, date__lt=nxt).exclude(status=Delivery.CANCELLED))
    del_sum = {"n": len(dels), "goods": sum((x.goods for x in dels), Z), "fees": sum((x.fee for x in dels), Z),
               "open": sum(1 for x in dels if x.status == Delivery.OUT)}
    if del_sum["open"]:
        checks.append(f"{del_sum['open']} delivery(ies) from this month still out with a driver (money not checked in).")

    # ------------------------------------------------------------------ stock
    if m["cos_from"] != "stock":
        checks.append("No final stock take at the start and end of the month – cost of sales is worked out from the "
                      "recipes, not from stock. Do a stock take on the last day of the month.")

    if m["sales"] and (m["cos"] < 0 or (m["gross_pct"] is not None and m["gross_pct"] > Decimal("0.9"))):
        checks.append(f"Cost of sales is {'negative' if m['cos'] < 0 else 'very low'} ({m['cos']:,.2f}) – check the stock take "
                      "values and that all supplier deliveries (GRVs) were typed.")
    if m["sales"] and m["gross_pct"] is not None and m["gross_pct"] < Decimal("0.2"):
        checks.append("Gross profit is below 20% of sales – check the stock takes, purchases and sales typed.")

    # ------------------------------------------------------------------ equipment
    items = list(Item.objects.select_related("category"))
    added = [i for i in items if start <= i.purchase_date <= end]
    disposed = [i for i in items if i.disposed_on and start <= i.disposed_on <= end]
    eq_cat = defaultdict(lambda: [Z, Z, Z])
    for i in items:
        r = eq_cat[i.category.name]
        if i.purchase_date <= end:
            r[0] += i.total_cost
        r[1] += i.dep_in(start)
        r[2] += i.book_value(start)
    eq_rows = sorted(((k, *v) for k, v in eq_cat.items()), key=lambda x: -x[1])
    eq_tot = [sum((r[n] for r in eq_rows), Z) for n in (1, 2, 3)]

    # ------------------------------------------------------------------ VAT summary
    vat_out_till = tot_days["vat"]
    vat_in_grv, vat_in_exp = grv_tot["vat"], exp_tot["vat"]
    vat = {"out_till": vat_out_till, "out_inv_other": inv_other_tot["vat"], "in_grv": vat_in_grv, "in_exp": vat_in_exp,
           "out": vat_out_till + inv_other_tot["vat"], "in": vat_in_grv + vat_in_exp}
    vat["net"] = vat["out"] - vat["in"]
    vat_days = sum(1 for r in days if r["vat"] is not None)

    return {"m": m, "start": start, "end": end, "cs": cs, "checks": checks, "days": days, "tot_days": tot_days,
            "by_category": by_category, "cat_total": sum((v for _, v in by_category), Z), "methods": methods,
            "methods_total": sum((v for _, v in methods), Z),
            "exp_rows": exp_rows, "exp_tot": exp_tot, "by_paid": sorted(by_paid.items(), key=lambda x: -x[1]),
            "grv_rows": grv_rows, "grv_tot": grv_tot, "by_supplier": by_supplier,
            "pay": pay, "runs": runs,
            "inv_rows": inv_rows, "inv_tot": inv_tot, "inv_cancelled": cancelled, "inv_other_tot": inv_other_tot,
            "deb_rows": deb_rows, "deb_tot": deb_tot, "del_sum": del_sum,
            "added": added, "disposed": disposed, "eq_rows": eq_rows, "eq_tot": eq_tot,
            "vat": vat, "vat_days": vat_days, "with_payroll": with_payroll}
