"""What the bakery needs to sell – the same maths as the Excel 'Staff & Costs' and 'Dashboard' sheets.

costs per month   = staff wages (Staff) + overheads (Costs & targets)
per week          = per month ÷ (52 ÷ 12)          per day = per week ÷ trading days per week
break-even sales  = costs ÷ GP %                    (sales excl. VAT that just pay all the costs)
break-even+profit = (costs + profit I want) ÷ GP %
"""
from collections import defaultdict
from decimal import Decimal

from .models import CompanySettings, Overhead

Z = Decimal("0")
WEEKS_PER_MONTH = Decimal(52) / Decimal(12)


def monthly_wages():
    """Monthly pay of everybody working here (salary or day/hour rate worked out per month) + allowances."""
    from staff.models import Employee, PayrollSettings

    cs = CompanySettings.get()
    ps = PayrollSettings.get()
    days = Decimal(cs.trading_days or 6) * WEEKS_PER_MONTH
    total = Z
    n = 0
    for e in Employee.objects.filter(active=True):
        n += 1
        if e.pay_type == "monthly":
            total += e.rate
        elif e.pay_type == "daily":
            total += e.rate * days
        else:
            total += e.rate * ps.normal_hours
        total += e.allowances
    return total, n


def product_gps(calc=None):
    """GP % of every product with a selling price, grouped by category: ({category_id: avg}, overall avg)."""
    from costing.calc import Calculator, CycleError
    from costing.models import Recipe

    calc = calc or Calculator().preload()
    by_cat = defaultdict(list)
    every = []
    for r in Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__isnull=False):
        try:
            gp = calc.gp(r)
        except CycleError:
            gp = None
        if gp is None:
            continue
        by_cat[r.category_id].append(gp)
        every.append(gp)
    avg = (sum(every) / len(every)) if every else Decimal("0.55")
    return {k: sum(v) / len(v) for k, v in by_cat.items()}, avg


class Targets:
    def __init__(self, gp_avg=None):
        cs = CompanySettings.get()
        self.settings = cs
        self.trading_days = Decimal(cs.trading_days or 6)
        self.wages, self.staff_count = monthly_wages()
        self.overheads = sum((o.monthly_cost for o in Overhead.objects.all()), Z)
        self.costs_month = self.wages + self.overheads
        self.costs_week = self.costs_month / WEEKS_PER_MONTH
        self.costs_day = self.costs_week / self.trading_days
        self.profit_month = cs.profit_target or Z
        self.profit_week = self.profit_month / WEEKS_PER_MONTH
        self.profit_day = self.profit_week / self.trading_days
        if cs.gp_override is not None:
            self.gp, self.gp_from = cs.gp_override, "set"
        else:
            if gp_avg is None:
                gp_avg = product_gps()[1]
            self.gp, self.gp_from = gp_avg, "products"
        g = self.gp if self.gp and self.gp > 0 else None
        self.be_day = self.costs_day / g if g else None
        self.be_week = self.costs_week / g if g else None
        self.be_month = self.costs_month / g if g else None
        self.bep_day = (self.costs_day + self.profit_day) / g if g else None
        self.bep_week = (self.costs_week + self.profit_week) / g if g else None
        self.bep_month = (self.costs_month + self.profit_month) / g if g else None

    def rows(self):
        return [
            ("Costs", self.costs_day, self.costs_week, self.costs_month),
            ("Profit I want", self.profit_day, self.profit_week, self.profit_month),
            ("Break-even", self.be_day, self.be_week, self.be_month),
            ("Break-even + profit", self.bep_day, self.bep_week, self.bep_month),
        ]
