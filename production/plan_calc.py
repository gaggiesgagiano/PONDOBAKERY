"""Turns a production plan into batches, mother recipes to prepare, and the ingredients to take from the store."""
from decimal import Decimal

from costing.calc import Calculator
from costing.models import WEIGHT_UNITS, Ingredient

ZERO = Decimal("0")
MAX_DEPTH = 6


class PlanResult:
    def __init__(self, plan, calc=None):
        self.calc = calc or Calculator().preload()
        self.plan = plan
        self.products = []      # dicts: line, units, yield, batches, factor
        self.prepare = {}       # mother recipe -> {"recipe", "ingredient", "qty", "unit", "for": set()}
        self.ingredients = {}   # bought ingredient -> {"ingredient", "qty", "cost", "for": set()}
        self.problems = []
        for ln in plan.lines.select_related("recipe", "recipe__category"):
            units = Decimal(ln.units)
            y = self.calc.batch_yield(ln.recipe)
            row = {"line": ln, "units": ln.units, "yield": y, "batches": None}
            if units and y:
                factor = units / y
                row["batches"] = factor
                self._explode(ln.recipe, factor, ln.recipe.name, 0)
            elif units and not y:
                self.problems.append(f"{ln.recipe.name}: no batch yield set, so ingredients can't be worked out.")
            self.products.append(row)

    def _explode(self, recipe, factor, top, depth):
        if depth > MAX_DEPTH:
            self.problems.append(f"{recipe.name}: mother recipes nested too deep – check for a loop.")
            return
        for ln in self.calc.lines(recipe):
            qty = self.calc.line_qty(recipe, ln) * factor
            ing = ln.ingredient
            if not qty:
                continue
            if ing.kind == Ingredient.SUBRECIPE and ing.recipe_id:
                sub = ing.recipe
                p = self.prepare.setdefault(sub.pk, {"recipe": sub, "ingredient": ing, "qty": ZERO, "for": set()})
                p["qty"] += qty
                p["for"].add(top)
                # how many batches of the mother recipe that is
                per = self.calc.finished_weight(sub) if ing.unit in WEIGHT_UNITS else self.calc.units(sub)
                if per:
                    self._explode(sub, qty / per, top, depth + 1)
                else:
                    self.problems.append(f"{sub.name}: no weight or yield, so its ingredients can't be worked out.")
            else:
                d = self.ingredients.setdefault(ing.pk, {"ingredient": ing, "qty": ZERO, "cost": ZERO, "for": set()})
                d["qty"] += qty
                uc = self.calc.unit_cost(ing)
                if uc:
                    d["cost"] += qty * uc
                d["for"].add(top)

    @property
    def total_units(self):
        return sum(p["units"] for p in self.products)

    @property
    def ingredient_rows(self):
        def key(d):
            i = d["ingredient"]
            return (0 if i.kind == Ingredient.BOUGHT else 1, (i.supplier.name if i.supplier else "zzz").lower(), i.name.lower())
        return sorted(self.ingredients.values(), key=key)

    @property
    def prepare_rows(self):
        rows = sorted(self.prepare.values(), key=lambda d: d["recipe"].name.lower())
        for d in rows:
            d["batches"] = None
            per = self.calc.finished_weight(d["recipe"]) if d["ingredient"].unit in WEIGHT_UNITS else self.calc.units(d["recipe"])
            if per:
                d["batches"] = d["qty"] / per
        return rows

    @property
    def total_cost(self):
        return sum((d["cost"] for d in self.ingredients.values()), ZERO)
