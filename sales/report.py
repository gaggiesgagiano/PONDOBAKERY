"""Month figures used by the sales report, the dashboard and the waste summary."""
import datetime
from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum

from core.models import CompanySettings

from .models import CashUp, CashUpLine, DailySales, Expense, SaleLine

Z = Decimal("0")


def month_bounds(month):
    start = month.replace(day=1)
    nxt = (start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return start, nxt


def parse_month(s, today):
    try:
        return datetime.date.fromisoformat((s or "") + "-01")
    except ValueError:
        return today.replace(day=1)


def sales_total(start, end):
    """Sales excl. VAT (Daily sales) for dates start <= d < end."""
    return DailySales.objects.filter(date__gte=start, date__lt=end).aggregate(s=Sum("total"))["s"] or Z


def excl_ratio(start, end):
    """Share of sales that is not VAT. From the product sales typed for the period if there are any,
    otherwise from the normal VAT rate in Settings. Returns (ratio, based_on_products)."""
    incl = excl = Z
    for ln in SaleLine.objects.filter(day__date__gte=start, day__date__lt=end):
        incl += ln.qty * ln.price
        excl += ln.value_excl
    if incl:
        return excl / incl, True
    return 1 / (1 + CompanySettings.get().vat_rate), False


def month_report(month):
    start, nxt = month_bounds(month)
    cus = list(CashUp.objects.filter(date__gte=start, date__lt=nxt))
    by_day = defaultdict(lambda: Z)
    for ds in DailySales.objects.filter(date__gte=start, date__lt=nxt):
        by_day[ds.date] += ds.total
    days = []
    d = start
    while d < nxt:
        days.append((d, by_day.get(d, Z)))
        d += datetime.timedelta(days=1)
    total = sum(by_day.values(), Z)
    taken = sum((c.total_sales for c in cus), Z)
    variance = sum((c.total_variance for c in cus), Z)
    methods = (CashUpLine.objects.filter(cashup__date__gte=start, cashup__date__lt=nxt)
               .values("method__name").annotate(t=Sum("till_amount")).order_by("-t"))
    total_excl = total
    on_products = True

    exp = (Expense.objects.filter(date__gte=start, date__lt=nxt).values("category__name")
           .annotate(t=Sum("amount")).order_by("-t"))
    expenses = sum((e["t"] for e in exp), Z)

    # deliveries (stock bought)
    from stock.models import GRVLine
    purchases = purchases_excl = Z
    for ln in GRVLine.objects.filter(grv__date__gte=start, grv__date__lt=nxt).select_related("ingredient"):
        purchases += ln.line_total
        purchases_excl += ln.value_excl

    # waste at cost
    from production.models import WasteLine
    waste = sum((ln.line_cost for ln in WasteLine.objects.filter(log__date__gte=start, log__date__lt=nxt)), Z)

    # wages (final pay runs for this month)
    from staff.models import PayRun
    wages = wages_cost = Z
    runs = list(PayRun.objects.filter(period__gte=start, period__lt=nxt).exclude(status=PayRun.DRAFT))
    for run in runs:
        t = run.totals()
        wages += t["gross"]
        wages_cost += t["cost"]
    draft_runs = PayRun.objects.filter(period__gte=start, period__lt=nxt, status=PayRun.DRAFT).count()

    # products
    prod = defaultdict(lambda: {"qty": Z, "value": Z, "excl": Z, "cost": Z})
    for ln in SaleLine.objects.filter(day__date__gte=start, day__date__lt=nxt).select_related("recipe"):
        p = prod[ln.recipe]
        p["qty"] += ln.qty
        p["value"] += ln.value
        p["excl"] += ln.value_excl
        p["cost"] += ln.cost
    products = []
    for r, p in prod.items():
        p["gp"] = (p["excl"] - p["cost"]) / p["excl"] if p["excl"] else None
        products.append((r, p))
    products.sort(key=lambda x: -x[1]["value"])
    prod_excl = sum((p["excl"] for _, p in products), Z)
    prod_cost = sum((p["cost"] for _, p in products), Z)

    profit = total_excl - purchases_excl - expenses - wages_cost
    return {
        "month": start, "next": nxt, "days": days, "biggest": max([v for _, v in days] + [Decimal("1")]),
        "n_cashups": len(cus), "trading_days": len(by_day), "total": total, "total_excl": total_excl, "taken": taken,
        "on_products": on_products, "variance": variance, "methods": list(methods),
        "expenses_by_cat": list(exp), "expenses": expenses,
        "purchases": purchases, "purchases_excl": purchases_excl, "waste": waste,
        "waste_pct": (waste / total_excl) if total_excl else None,
        "wages": wages, "wages_cost": wages_cost, "pay_runs": len(runs), "draft_runs": draft_runs,
        "products": products[:20], "n_products": len(products), "prod_excl": prod_excl, "prod_cost": prod_cost,
        "prod_gp": ((prod_excl - prod_cost) / prod_excl) if prod_excl else None,
        "profit": profit,
        "avg_day": (total / len(by_day)) if by_day else None,
    }
