"""Stock on hand = last final stock take + deliveries (GRVs) since − what was used since.

What "used" means is a setting (Settings › Costs & targets, or the stock take page):
* sales  – every product sold on the Pondo till, and every product logged as waste, takes its ingredients
           out of stock (worked out from the recipes, mother recipes included). Refunds put them back.
* production – a production plan marked Done takes its ingredients out of stock.
"""
from collections import defaultdict
from decimal import ROUND_CEILING, Decimal

from django.utils import timezone

from costing.calc import Calculator
from costing.models import Ingredient
from production.models import PlanUsage

from .models import GRV, CountLine, GRVLine, StockCount

Z = Decimal("0")


def usage_mode():
    from core.models import CompanySettings
    return getattr(CompanySettings.get(), "stock_usage", "sales") or "sales"


def base_time(c):
    """The moment a final stock take stands for: when counting started (or, for old ones, when it was finalised)."""
    return c.as_at or c.finalized_at


def last_count(before=None):
    qs = StockCount.objects.filter(status=StockCount.FINAL)
    counts = sorted(qs, key=lambda c: base_time(c) or timezone.now(), reverse=True)
    for c in counts:
        if before is None or (base_time(c) and base_time(c) <= before):
            return c
    return None


def explode(units_by_recipe, calc=None):
    """{recipe: units} -> {ingredient_id: qty} of bought / packaging ingredients, through mother recipes."""
    from production.plan_calc import PlanResult

    calc = calc or Calculator().preload()
    pr = PlanResult.__new__(PlanResult)
    pr.calc, pr.prepare, pr.ingredients, pr.problems, pr.products = calc, {}, {}, [], []
    for recipe, units in units_by_recipe.items():
        if not units:
            continue
        y = calc.batch_yield(recipe)
        if y:
            pr._explode(recipe, Decimal(units) / y, recipe.name, 0)
    return {k: d["qty"] for k, d in pr.ingredients.items()}


def sold_and_wasted(start, end):
    """{recipe: units} sold on the till (refunds take off) and logged as waste between start (excl.) and end (incl.)."""
    from production.models import WasteLine
    from till.models import SaleItem

    units = defaultdict(lambda: Z)
    items = SaleItem.objects.select_related("recipe")
    waste = WasteLine.objects.select_related("recipe")
    if start:
        items = items.filter(sale__created_at__gt=start)
        waste = waste.filter(log__created_at__gt=start)
    if end:
        items = items.filter(sale__created_at__lte=end)
        waste = waste.filter(log__created_at__lte=end)
    for it in items:
        units[it.recipe] += it.qty
    for w in waste:
        units[w.recipe] += w.qty
    return units


def on_hand_all(as_at=None):
    """({ingredient_id: qty in recipe units}, last final count) – now, or as at a moment in time."""
    qty = defaultdict(lambda: Z)
    lc = last_count(as_at)
    start = base_time(lc) if lc else None
    grvs = GRVLine.objects.select_related("ingredient")
    if lc:
        for cl in CountLine.objects.filter(count=lc, ingredient__isnull=False):
            qty[cl.ingredient_id] += cl.qty
        grvs = grvs.filter(grv__created_at__gt=start)
    if as_at:
        grvs = grvs.filter(grv__created_at__lte=as_at)
    for gl in grvs:
        qty[gl.ingredient_id] += gl.packs * gl.ingredient.pack_size
    if usage_mode() == "production":
        usage = PlanUsage.objects.filter(plan__done_at__isnull=False)
        if start:
            usage = usage.filter(plan__done_at__gt=start)
        if as_at:
            usage = usage.filter(plan__done_at__lte=as_at)
        for u in usage:
            qty[u.ingredient_id] -= u.qty
    else:
        for ing_id, q in explode(sold_and_wasted(start, as_at)).items():
            qty[ing_id] -= q
    return qty, lc


def stock_rows(supplier=None, low_only=False):
    calc = Calculator().preload()
    qty, lc = on_hand_all()
    qs = Ingredient.objects.filter(active=True).exclude(kind=Ingredient.SUBRECIPE).select_related("supplier")
    if supplier:
        qs = qs.filter(supplier=supplier)
    rows = []
    for i in qs:
        q = qty.get(i.pk, Z)
        uc = calc.unit_cost(i) or Z
        low = i.reorder_level is not None and q < i.reorder_level
        if low_only and not low:
            continue
        rows.append({"i": i, "qty": q, "packs": (q / i.pack_size) if i.pack_size else None, "value": q * uc, "low": low,
                     "suggest": suggest_packs(i, q)})
    return rows, lc


def suggest_packs(i, q):
    """Packs to order to get back up to 'order up to' (or re-order level) – None if not needed."""
    target = i.stock_par if i.stock_par is not None else i.reorder_level
    if target is None or not i.pack_size or q >= (i.reorder_level if i.reorder_level is not None else target):
        return None
    need = (target - q) / i.pack_size
    return need.to_integral_value(rounding=ROUND_CEILING) if need > 0 else None


def purchases_between(start_exclusive, end_inclusive):
    qs = GRV.objects.prefetch_related("lines__ingredient")
    if start_exclusive:
        qs = qs.filter(date__gt=start_exclusive)
    if end_inclusive:
        qs = qs.filter(date__lte=end_inclusive)
    return sum((g.total_excl for g in qs), Z)
