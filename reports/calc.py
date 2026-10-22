"""Month-end and cost-of-sales figures – the Excel 'Month-End Report', 'COGS' and 'COGS Weekly Log' sheets.

Cost of sales (real)        = opening stock + purchases − closing stock   (needs final stock takes)
Cost of sales (recipes)     = sales − gross profit worked out from the recipes ("theoretical")
Unexplained loss / (gain)   = real − recipes − waste logged   (theft, over-portioning, counting errors …)
Net profit                  = sales − cost of sales − wages − running expenses − equipment depreciation
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from core.models import CompanySettings, Overhead
from core.targets import monthly_wages

Z = Decimal("0")
CASUAL = "casual wages & overtime"
STAFF_MEALS = "Staff / tasting"


def month_bounds(month):
    start = month.replace(day=1)
    nxt = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return start, nxt


def _final_counts():
    from stock.models import StockCount

    return list(StockCount.objects.filter(status=StockCount.FINAL, total_value__isnull=False).order_by("date", "id"))


def _purchases(after, upto):
    """Deliveries (GRVs) after one date up to and including another: total excl. VAT, VAT and per supplier."""
    from stock.models import GRVLine

    qs = GRVLine.objects.select_related("ingredient", "grv__supplier")
    if after:
        qs = qs.filter(grv__date__gt=after)
    if upto:
        qs = qs.filter(grv__date__lte=upto)
    total = vat = Z
    by_sup = defaultdict(lambda: Z)
    for ln in qs:
        ex = ln.value_excl
        total += ex
        vat += ln.line_total - ex
        by_sup[ln.grv.supplier.name] += ex
    return total, vat, sorted(by_sup.items(), key=lambda x: -x[1])


def _sales(after, upto):
    """Daily sales (excl. VAT) and the gross profit the recipes say they made."""
    from sales.models import DailySales

    qs = DailySales.objects.all()
    if after:
        qs = qs.filter(date__gt=after)
    if upto:
        qs = qs.filter(date__lte=upto)
    agg = qs.aggregate(s=Sum("total"), g=Sum("gp_amount"))
    return agg["s"] or Z, agg["g"] or Z, qs.count()


def _waste(after, upto):
    from production.models import WasteLine

    qs = WasteLine.objects.all()
    if after:
        qs = qs.filter(log__date__gt=after)
    if upto:
        qs = qs.filter(log__date__lte=upto)
    waste = meals = Z
    for ln in qs:
        if ln.reason == STAFF_MEALS:
            meals += ln.line_cost
        else:
            waste += ln.line_cost
    return waste, meals


def stock_period(prev, cur):
    """Everything between two final stock takes."""
    purch, _, by_sup = _purchases(prev.date, cur.date)
    sales, gp_recipes, days = _sales(prev.date, cur.date)
    waste, meals = _waste(prev.date, cur.date)
    cos = prev.total_value + purch - cur.total_value
    theo_cos = sales - gp_recipes
    n_days = (cur.date - prev.date).days
    avg_stock = (prev.total_value + cur.total_value) / 2
    return {
        "prev": prev, "cur": cur, "days": n_days, "opening": prev.total_value, "purchases": purch, "by_supplier": by_sup,
        "closing": cur.total_value, "cos": cos, "sales": sales, "sales_days": days,
        "gp": sales - cos, "gp_pct": ((sales - cos) / sales) if sales else None,
        "theo_cos": theo_cos, "theo_gp_pct": (gp_recipes / sales) if sales else None,
        "waste": waste, "meals": meals,
        "unexplained": (cos - theo_cos - waste - meals) if sales else None,
        "turnover": (cos / avg_stock) if avg_stock else None,
        "days_on_hand": (avg_stock / (cos / n_days)) if (cos > 0 and n_days) else None,
    }


def stock_results(month):
    """Stock-take periods that END in the month (one per stock take – weekly if you count weekly)."""
    start, nxt = month_bounds(month)
    counts = _final_counts()
    periods = []
    for i, c in enumerate(counts):
        if i and start <= c.date < nxt:
            periods.append(stock_period(counts[i - 1], c))
    tot = {k: sum((p[k] for p in periods), Z) for k in ("purchases", "cos", "sales", "theo_cos", "waste", "meals")}
    tot["gp"] = tot["sales"] - tot["cos"]
    tot["gp_pct"] = (tot["gp"] / tot["sales"]) if tot["sales"] else None
    tot["theo_gp_pct"] = ((tot["sales"] - tot["theo_cos"]) / tot["sales"]) if tot["sales"] else None
    tot["unexplained"] = (tot["cos"] - tot["theo_cos"] - tot["waste"] - tot["meals"]) if tot["sales"] else None
    target = CompanySettings.get().target_gp
    tot["sales_needed"] = (tot["cos"] / (1 - target)) if target < 1 else None
    tot["gp_short"] = (tot["gp"] - tot["sales"] * target) if tot["sales"] else None
    sup = defaultdict(lambda: Z)
    for p in periods:
        for name, v in p["by_supplier"]:
            sup[name] += v
    return {"periods": periods, "tot": tot, "target": target, "by_supplier": sorted(sup.items(), key=lambda x: -x[1]),
            "n_counts": len(counts)}


def depreciation_for(month):
    try:
        from equipment.calc import depreciation_for_month
    except ImportError:
        return None
    return depreciation_for_month(month)


def month_end(month):
    from sales.models import CashUp, CashUpLine, DailySales, Expense
    from staff.models import PayRun

    start, nxt = month_bounds(month)
    end = nxt - datetime.timedelta(days=1)
    cs = CompanySettings.get()

    # ---- sales
    days = list(DailySales.objects.filter(date__gte=start, date__lt=nxt))
    sales = sum((d.total for d in days), Z)
    gp_recipes = sum((d.gp_amount for d in days), Z)
    best = max(days, key=lambda d: d.total) if days else None

    # ---- stock & cost of sales
    counts = _final_counts()
    opening = next((c for c in reversed(counts) if c.date < start), None)
    closing = next((c for c in reversed(counts) if start <= c.date <= end), None)
    if opening is None and closing is not None:
        opening = next((c for c in counts if start <= c.date < closing.date), None)
    if opening and closing and opening.date < closing.date:
        purch, purch_vat, by_sup = _purchases(opening.date, closing.date)
        cos = opening.total_value + purch - closing.total_value
        cos_from = "stock"
    else:
        purch, purch_vat, by_sup = _purchases(start - datetime.timedelta(days=1), end)
        cos = sales - gp_recipes
        cos_from = "recipes"
    gross = sales - cos

    # ---- wages
    runs = list(PayRun.objects.filter(period__gte=start, period__lt=nxt).exclude(status=PayRun.DRAFT))
    if runs:
        wages = sum((r.totals()["cost"] for r in runs), Z)
        wages_from = "payroll"
    else:
        wages = monthly_wages()[0]
        wages_from = "staff"
    exps = list(Expense.objects.filter(date__gte=start, date__lt=nxt).select_related("category"))
    casual = sum((e.amount_excl for e in exps if e.category.name.lower() == CASUAL), Z)

    # ---- running expenses (actual, or the budget when nothing was typed)
    running_list = [e for e in exps if e.category.name.lower() != CASUAL]
    budget = sum((o.monthly_cost for o in Overhead.objects.all()), Z)
    if running_list:
        running = sum((e.amount_excl for e in running_list), Z)
        running_from = "actual"
    else:
        running = budget
        running_from = "budget"
    by_cat = defaultdict(lambda: Z)
    for e in exps:
        by_cat[e.category.name] += e.amount_excl
    dep = depreciation_for(start)

    expenses = wages + casual + running + (dep or Z)
    net = gross - expenses

    # ---- cash
    cus = list(CashUp.objects.filter(date__gte=start, date__lt=nxt))
    methods = list(CashUpLine.objects.filter(cashup__date__gte=start, cashup__date__lt=nxt)
                   .values("method__name").annotate(t=Sum("till_amount")).order_by("-t"))
    taken = sum((c.total_sales for c in cus), Z)
    payouts = Expense.objects.filter(cashup__date__gte=start, cashup__date__lt=nxt).aggregate(s=Sum("amount"))["s"] or Z
    banked = sum((c.banked or Z for c in cus), Z)

    # VAT in the till: only days that have BOTH a cash-up and daily sales, otherwise the two don't compare
    sales_by_day = defaultdict(lambda: Z)
    for d in days:
        sales_by_day[d.date] += d.total
    both = {c.date for c in cus} & set(sales_by_day)
    vat_sales = None
    if both:
        vat_sales = (sum((c.total_sales for c in cus if c.date in both), Z)
                     - sum((sales_by_day[x] for x in both), Z))

    waste, meals = _waste(start - datetime.timedelta(days=1), end)
    try:
        from equipment.calc import count_summary
        from equipment.models import Item
        equip = count_summary(start) if Item.objects.exists() else None
        book = sum((i.book_value(start) for i in Item.objects.select_related("category")), Z) if equip else None
    except ImportError:
        equip = book = None
    pct = lambda v: (v / sales) if sales else None  # noqa: E731
    return {
        "month": start, "end": end, "sales": sales, "trading_days": len(days), "avg_day": (sales / len(days)) if days else None,
        "best": best, "gp_recipes_pct": (gp_recipes / sales) if sales else None,
        "opening": opening, "closing": closing, "purchases": purch, "purchases_vat": purch_vat, "by_supplier": by_sup,
        "cos": cos, "cos_from": cos_from, "gross": gross, "gross_pct": pct(gross),
        "stock_change": (closing.total_value - opening.total_value) if (opening and closing and cos_from == "stock") else None,
        "wages": wages, "wages_from": wages_from, "pay_runs": len(runs), "casual": casual,
        "running": running, "running_from": running_from, "budget": budget,
        "dep": dep, "expenses": expenses, "net": net, "net_before_dep": net + (dep or Z),
        "target": cs.profit_target, "vs_target": net - cs.profit_target,
        "pcts": {"cos": pct(cos), "wages": pct(wages), "casual": pct(casual), "running": pct(running),
                 "dep": pct(dep or Z), "expenses": pct(expenses), "net": pct(net)},
        "by_cat": sorted(by_cat.items(), key=lambda x: -x[1]), "exp_total": sum(by_cat.values(), Z),
        "running_vs_budget": budget - sum((e.amount_excl for e in running_list), Z),
        "n_cashups": len(cus), "cash_days": len({c.date for c in cus}), "days_in_month": end.day,
        "taken": taken, "methods": methods, "till_variance": sum((c.total_variance for c in cus), Z),
        "payouts": payouts, "banked": banked,
        "vat_expenses": sum((e.vat for e in exps), Z), "vat_sales": vat_sales, "vat_days": len(both),
        "waste": waste, "meals": meals, "waste_pct": pct(waste), "equip": equip, "equip_book": book,
    }


def snapshot(m):
    """The figures kept when a month is locked (as text, so they never change)."""
    keys = ["sales", "cos", "gross", "wages", "casual", "running", "dep", "net", "purchases", "waste", "taken",
            "banked", "till_variance", "vat_expenses"]
    out = {k: str((m[k] or Z).quantize(Decimal("0.01"))) if m[k] is not None else "" for k in keys}
    out["gross_pct"] = str(round(m["gross_pct"], 4)) if m["gross_pct"] is not None else ""
    out["closing_stock"] = str(m["closing"].total_value) if m["closing"] else ""
    out["cos_from"] = m["cos_from"]
    return out
