import datetime
from collections import defaultdict
from decimal import Decimal

from .models import EquipmentCount, Item

Z = Decimal("0")


def depreciation_for_month(month):
    """Total depreciation of all equipment for the month (used by the Month-end report)."""
    items = list(Item.objects.select_related("category"))
    if not items:
        return None
    return sum((i.dep_in(month.replace(day=1)) for i in items), Z)


def year_schedule(first_month):
    """Depreciation for 12 months from 'first_month', per category and in total."""
    months = []
    m = first_month.replace(day=1)
    for _ in range(12):
        months.append(m)
        m = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    rows = defaultdict(lambda: [Z] * 12)
    for i in Item.objects.select_related("category"):
        for n, mm in enumerate(months):
            rows[i.category.name][n] += i.dep_in(mm)
    totals = [sum((r[n] for r in rows.values()), Z) for n in range(12)]
    out = sorted(((k, v, sum(v, Z)) for k, v in rows.items() if any(v)), key=lambda x: -x[2])
    return {"months": months, "rows": out, "totals": totals, "year": sum(totals, Z),
            "avg": sum(totals, Z) / 12}


def count_summary(month):
    """How the equipment count of a month looks: missing items and their value."""
    c = EquipmentCount.objects.filter(month=month.replace(day=1)).first()
    items = list(Item.objects.select_related("category", "location"))
    should = [i for i in items if i.expected_qty(month) > 0]
    counted = {ln.item_id: ln.qty for ln in c.lines.all()} if c else {}
    missing = []
    for i in should:
        if i.pk in counted and counted[i.pk] < i.expected_qty(month):
            n = i.expected_qty(month) - counted[i.pk]
            missing.append((i, n, n * i.unit_cost))
    written_off = [i for i in items if i.disposed_on and i.disposed_on.year == month.year and i.disposed_on.month == month.month]
    return {"count": c, "should": len(should), "counted": sum(1 for i in should if i.pk in counted),
            "not_counted": sum(1 for i in should if i.pk not in counted), "missing": missing,
            "missing_pieces": sum(n for _, n, _ in missing), "missing_value": sum((v for _, _, v in missing), Z),
            "written_off": written_off, "written_off_cost": sum((i.total_cost for i in written_off), Z)}
