"""Figures for the daily dashboard – the Excel 'Dashboard' sheet, section by section."""
import calendar
import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from .models import CompanySettings
from .targets import Targets, product_gps

Z = Decimal("0")
ONE = datetime.timedelta(days=1)


def _round_days(days, td):
    return int((Decimal(days) * Decimal(td) / 7).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _periods(d):
    monday = d - datetime.timedelta(days=d.weekday())
    return {"today": (d, d), "week": (monday, d), "month": (d.replace(day=1), d)}


def sales_block(d, t):
    from sales.models import DailySales

    out = {}
    for key, (a, b) in _periods(d).items():
        rows = list(DailySales.objects.filter(date__gte=a, date__lte=b).values_list("total", "gp_amount"))
        sales = sum((r[0] for r in rows), Z)
        gp_amt = sum((r[1] for r in rows), Z)
        logged = len(rows)
        mult = 1 if key == "today" else logged
        be = (t.be_day or Z) * mult
        bep = (t.bep_day or Z) * mult
        out[key] = {
            "sales": sales, "gp_amount": gp_amt, "gp": (gp_amt / sales) if sales else None, "days": logged,
            "be": be, "over_be": sales - be, "bep": bep, "over_bep": sales - bep,
            "net": gp_amt - t.costs_day * mult,
        }
    return out


def month_status(s):
    m = s["month"]
    if not m["days"]:
        return "none", "No sales typed this month yet"
    if m["over_be"] < 0:
        return "low", f"Below break-even – ${-m['over_be']:,.0f} short so far"
    if m["over_bep"] < 0:
        return "mid", f"Above break-even, but ${-m['over_bep']:,.0f} short of your profit target so far"
    return "ok", f"On target – ${m['over_bep']:,.0f} above break-even + profit so far"


def rest_of_month(d, t, sold):
    dim = calendar.monthrange(d.year, d.month)[1]
    end = d.replace(day=dim)
    td = t.trading_days
    left = _round_days((end - d).days, td)
    rows = []
    for label, goal in (("Break-even (covers costs)", t.be_month), ("Break-even + profit", t.bep_month)):
        if goal is None:
            continue
        still = max(Z, goal - sold)
        rows.append({"label": label, "goal": goal, "sold": sold, "still": still,
                     "per_day": (still / left) if left else None,
                     "pct": min(Decimal(100), sold / goal * 100) if goal else Z})
    return {"rows": rows, "days_left": left, "days_month": _round_days(dim, td)}


def categories_block(d):
    from sales.models import DailySalesLine

    p = _periods(d)
    data = defaultdict(lambda: {"today": Z, "week": Z, "month": Z})
    for ln in DailySalesLine.objects.filter(day__date__gte=p["month"][0], day__date__lte=d).select_related("category", "day"):
        row = data[ln.category]
        row["month"] += ln.amount
        if ln.day.date >= p["week"][0]:
            row["week"] += ln.amount
        if ln.day.date == d:
            row["today"] += ln.amount
    total = {k: sum((v[k] for v in data.values()), Z) for k in ("today", "week", "month")}
    rows = sorted(data.items(), key=lambda x: (-x[1]["month"], x[0].name))
    top = max([v["month"] for _, v in rows] + [Decimal("0.01")])
    for c, v in rows:
        v["share"] = (v["month"] / total["month"]) if total["month"] else None
    return {"rows": rows, "total": total, "top": top}


def waste_block(d, target):
    """Waste of the previous day (the day's waste is only complete after closing), its week and month."""
    from production.models import WASTE_REASONS, WasteLine, WasteLog
    from sales.models import DailySales

    prev = d - ONE
    p = _periods(prev)
    out = {"prev": prev, "logged": WasteLog.objects.filter(date=prev).exists(), "cols": {}, "reasons": []}
    reasons = defaultdict(lambda: {"today": Z, "week": Z, "month": Z})
    for key, (a, b) in p.items():
        cost = Z
        for ln in WasteLine.objects.filter(log__date__gte=a, log__date__lte=b).select_related("log"):
            c = ln.line_cost
            cost += c
            reasons[ln.reason][key] += c
        sales = sum(DailySales.objects.filter(date__gte=a, date__lte=b).values_list("total", flat=True), Z)
        pct = (cost / sales) if sales else None
        out["cols"][key] = {"cost": cost, "sales": sales, "pct": pct,
                            "over": (cost - target * sales) if sales else None}
    month_total = out["cols"]["month"]["cost"]
    for r in WASTE_REASONS:
        if r in reasons:
            v = reasons[r]
            v["share"] = (v["month"] / month_total) if month_total else None
            out["reasons"].append((r, v))
    pc = out["cols"]["today"]
    if not out["logged"]:
        out["status"] = ("none", f"No waste logged for {prev:%a %d %b}")
    elif pc["pct"] is None:
        out["status"] = ("none", f"Waste logged, but no sales typed for {prev:%a %d %b}")
    elif pc["pct"] > target:
        out["status"] = ("low", f"Over the {target * 100:.0f}% target")
    else:
        out["status"] = ("ok", f"Within the {target * 100:.0f}% target")
    return out


def staff_block(t, s):
    n = t.staff_count
    if not n:
        return None
    div = Decimal(n)

    def per(v):
        return None if v is None else v / div

    return {
        "n": n,
        "targets": [("Break-even sales per staff member", per(t.be_day), per(t.be_week), per(t.be_month)),
                    ("Break-even + profit per staff member", per(t.bep_day), per(t.bep_week), per(t.bep_month))],
        "actual": [("Sales per staff member", per(s["today"]["sales"]), per(s["week"]["sales"]), per(s["month"]["sales"])),
                   ("Over / (short) of break-even", per(s["today"]["over_be"]), per(s["week"]["over_be"]), per(s["month"]["over_be"])),
                   ("Over / (short) of profit target", per(s["today"]["over_bep"]), per(s["week"]["over_bep"]), per(s["month"]["over_bep"]))],
    }


def dashboard_data(d):
    from sales.models import CashUp, DailySales

    cs = CompanySettings.get()
    _, gp_avg = product_gps()
    t = Targets(gp_avg)
    s = sales_block(d, t)
    till = list(CashUp.objects.filter(date=d))
    return {
        "d": d, "t": t, "s": s, "status": month_status(s),
        "rest": rest_of_month(d, t, s["month"]["sales"]),
        "cats": categories_block(d), "waste": waste_block(d, cs.waste_target), "staff": staff_block(t, s),
        "typed": DailySales.objects.filter(date=d).exists(),
        "till_total": sum((c.total_sales for c in till), Z) if till else None,
        "till_variance": sum((c.total_variance for c in till), Z) if till else None,
        "cu_waiting": CashUp.objects.filter(signed_off_by__isnull=True).count(),
        "month_pct_be": (min(Decimal(100), s["month"]["sales"] / t.be_month * 100) if t.be_month else None),
        "month_pct_bep": (min(Decimal(100), s["month"]["sales"] / t.bep_month * 100) if t.bep_month else None),
        "be_marker": (t.be_month / t.bep_month * 100) if (t.be_month and t.bep_month) else None,
    }
