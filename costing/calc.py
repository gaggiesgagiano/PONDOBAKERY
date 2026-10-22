"""All recipe costing maths in one place.

Rules (same as the Excel master file, with its known faults fixed):
* Bought item cost per unit  = pack price / (1 + VAT) / pack size.
* Dough weight               = sum of the dough-section quantities.
* Batch yield                = typed yield, else floor(dough × (1 − weight loss) / scaling weight).
* Line quantity              = fixed, or per finished item × yield, or per kg × dough weight.
* Batch cost                 = sum of quantity × cost per unit for every line.
* Mother recipe cost         = per finished kg (batch cost / (dough × (1 − loss))) when the
                               ingredient is used by weight, else per finished item (batch cost / yield).
* Cost per unit (product)    = batch cost / yield (mother recipes: per finished kg).
* GP %                       = (selling price excl. VAT − cost per unit) / selling price excl. VAT.
"""
from decimal import ROUND_FLOOR, Decimal

from core.models import CompanySettings

from .models import WEIGHT_UNITS, Ingredient, Recipe, RecipeLine

ZERO = Decimal("0")


class CycleError(Exception):
    pass


class Calculator:
    """Works out costs, caching results for one screen/request."""

    def __init__(self, settings=None):
        self.settings = settings or CompanySettings.get()
        self._lines = {}
        self._cost = {}
        self._busy = set()

    # ---- data access -------------------------------------------------
    def lines(self, recipe):
        if recipe.pk not in self._lines:
            self._lines[recipe.pk] = list(
                RecipeLine.objects.filter(recipe=recipe).select_related("ingredient", "ingredient__recipe"))
        return self._lines[recipe.pk]

    def preload(self):
        """Load every line at once (for lists of all recipes)."""
        by = {}
        for ln in RecipeLine.objects.select_related("ingredient", "ingredient__recipe"):
            by.setdefault(ln.recipe_id, []).append(ln)
        for r in Recipe.objects.all():
            self._lines.setdefault(r.pk, by.get(r.pk, []))
        return self

    # ---- quantities --------------------------------------------------
    def dough_weight(self, r):
        return sum((ln.qty for ln in self.lines(r) if ln.section == RecipeLine.DOUGH and ln.qty_mode == RecipeLine.FIXED),
                   ZERO)

    def finished_weight(self, r):
        return self.dough_weight(r) * (1 - (r.weight_loss or ZERO))

    def batch_yield(self, r):
        if r.yield_override:
            return Decimal(r.yield_override)
        if r.scaling_weight:
            y = (self.finished_weight(r) / r.scaling_weight).to_integral_value(rounding=ROUND_FLOOR)
            return y
        return None

    def line_qty(self, r, ln):
        if ln.qty_mode == RecipeLine.PER_UNIT:
            return ln.qty * (self.batch_yield(r) or ZERO)
        if ln.qty_mode == RecipeLine.PER_KG:
            return ln.qty * self.dough_weight(r)
        return ln.qty

    # ---- costs -------------------------------------------------------
    def unit_cost(self, ing):
        """Cost per recipe unit of an ingredient, excl. VAT. None = no price yet."""
        if ing.kind == Ingredient.SUBRECIPE and ing.recipe_id:
            rec = ing.recipe
            if ing.unit in WEIGHT_UNITS:
                return self.cost_per_finished_kg(rec)
            return self.cost_per_unit(rec)
        return ing.bought_unit_cost()

    def batch_cost(self, r):
        if r.pk in self._cost:
            return self._cost[r.pk]
        if r.pk in self._busy:
            raise CycleError(f"'{r.name}' uses itself (directly or through a mother recipe).")
        self._busy.add(r.pk)
        try:
            total = ZERO
            for ln in self.lines(r):
                uc = self.unit_cost(ln.ingredient)
                if uc:
                    total += self.line_qty(r, ln) * uc
        finally:
            self._busy.discard(r.pk)
        self._cost[r.pk] = total
        return total

    def line_cost(self, r, ln):
        uc = self.unit_cost(ln.ingredient)
        return None if uc is None else self.line_qty(r, ln) * uc

    def cost_per_finished_kg(self, r):
        fw = self.finished_weight(r)
        return self.batch_cost(r) / fw if fw else None

    def units(self, r):
        """What one 'unit' of this recipe is for cost per unit: finished items, or kg for mother recipes."""
        y = self.batch_yield(r)
        if y:
            return y
        if r.is_subrecipe:
            fw = self.finished_weight(r)
            return fw or None
        return None

    def cost_per_unit(self, r):
        u = self.units(r)
        return self.batch_cost(r) / u if u else None

    # ---- selling -----------------------------------------------------
    def vat(self, r):
        return r.vat_rate if r.vat_rate is not None else self.settings.vat_rate

    def sell_excl(self, r):
        if r.sell_price is None:
            return None
        return Decimal(r.sell_price) / (1 + self.vat(r))

    def gp(self, r):
        s, c = self.sell_excl(r), self.cost_per_unit(r)
        if not s or c is None:
            return None
        return (s - c) / s

    def gp_amount(self, r):
        s, c = self.sell_excl(r), self.cost_per_unit(r)
        if s is None or c is None:
            return None
        return s - c

    def target_price(self, r, target=None):
        """Lowest selling price incl. VAT that reaches the target GP."""
        c = self.cost_per_unit(r)
        t = target if target is not None else self.settings.target_gp
        if c is None or t >= 1:
            return None
        return c / (1 - t) * (1 + self.vat(r))

    def summary(self, r):
        return {
            "dough": self.dough_weight(r),
            "finished": self.finished_weight(r),
            "yield": self.batch_yield(r),
            "batch_cost": self.batch_cost(r),
            "cpu": self.cost_per_unit(r),
            "cpkg": self.cost_per_finished_kg(r),
            "vat": self.vat(r),
            "sell_excl": self.sell_excl(r),
            "gp": self.gp(r),
            "gp_amount": self.gp_amount(r),
            "target_price": self.target_price(r),
        }
