"""Sales, cash-up and expenses.

* Cash-up  – one per till per day: what the till says per payment type, what was really
             counted, money paid out of the till, float, money banked. Shows over / short.
* Product sales – optional: how many of each product were sold on a day (from the till report).
             Gives real gross profit and best sellers.
* Expenses – every rand/dollar spent that is not a stock delivery (GRV): gas, electricity, rent,
             transport, repairs … Paid out of the till, from the bank, or by the owner.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from costing.models import Recipe

Z = Decimal("0")
C = Decimal("0.01")


class PaymentMethod(models.Model):
    name = models.CharField(max_length=60, unique=True)
    is_cash = models.BooleanField("Notes & coins in the till", default=False,
                                  help_text="Tick for cash. Cash is checked against what you count in the drawer.")
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=60, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class CashUp(models.Model):
    date = models.DateField()
    till = models.CharField("Till / shift", max_length=40, default="Main till")
    cashier = models.CharField("Cashier", max_length=80, blank=True)
    opening_float = models.DecimalField("Float at the start ($)", max_digits=10, decimal_places=2, default=Z)
    drops = models.DecimalField("Cash drops to the safe during the shift ($)", max_digits=12, decimal_places=2, default=Z,
                                help_text="Cash taken out of the drawer to the safe before closing (from the till)")
    cash_counted = models.DecimalField("Cash counted in the drawer ($)", max_digits=12, decimal_places=2,
                                       null=True, blank=True, help_text="All notes and coins at closing, float included")
    zig_counted = models.DecimalField("ZiG cash counted (in ZiG)", max_digits=14, decimal_places=2, null=True,
                                      blank=True, help_text="Only if customers paid in ZiG notes")
    zig_rate = models.DecimalField("ZiG rate (ZiG per US$1)", max_digits=10, decimal_places=4, null=True, blank=True)
    float_left = models.DecimalField("Float left for tomorrow ($)", max_digits=10, decimal_places=2, default=Z)
    banked = models.DecimalField("Cash taken to bank / safe ($)", max_digits=12, decimal_places=2, null=True,
                                 blank=True)
    notes = models.TextField(blank=True)
    # worked out when saved (so lists and reports are quick)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    total_variance = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    signed_off_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")
    signed_off_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "till"]
        constraints = [models.UniqueConstraint(fields=["date", "till"], name="one_cashup_per_till_per_day")]

    def __str__(self):
        return f"Cash-up {self.date:%d %b %Y} – {self.till}"

    @property
    def number(self):
        return f"CU-{self.pk:04d}"

    # ---- the maths ---------------------------------------------------
    def result(self):
        """Everything the cash-up screen and print show."""
        lines = list(self.lines.select_related("method"))
        payouts = sum((e.amount for e in self.expenses.all()), Z)
        cash_till = sum((ln.till_amount for ln in lines if ln.method.is_cash), Z)
        cash_taken = None
        zig_usd = self.zig_usd
        if self.cash_counted is not None or zig_usd:
            cash_taken = (self.cash_counted or Z) + (zig_usd or Z) + payouts + (self.drops or Z) - self.opening_float
        rows = []
        for ln in lines:
            if ln.method.is_cash:
                actual = None  # cash is checked in one go below
                var = None
            else:
                actual = ln.actual_amount
                var = None if actual is None else actual - ln.till_amount
            rows.append({"line": ln, "method": ln.method, "till": ln.till_amount, "actual": actual, "variance": var})
        cash_var = None if cash_taken is None else cash_taken - cash_till
        variance = (cash_var or Z) + sum((r["variance"] or Z for r in rows), Z)
        total_till = sum((ln.till_amount for ln in lines), Z)
        to_bank = None if self.cash_counted is None else self.cash_counted - self.float_left
        return {
            "rows": rows, "payouts": payouts, "cash_till": cash_till, "cash_taken": cash_taken,
            "cash_variance": cash_var, "variance": variance.quantize(C), "total_till": total_till,
            "to_bank": to_bank, "zig_usd": zig_usd,
            "bank_diff": None if (to_bank is None or self.banked is None) else self.banked - to_bank,
        }

    @property
    def zig_usd(self):
        """ZiG notes counted, in US$ at the day's rate."""
        if self.zig_counted and self.zig_rate:
            return (self.zig_counted / self.zig_rate).quantize(C)
        return None

    def refresh_totals(self):
        res = self.result()
        self.total_sales = res["total_till"]
        self.total_variance = res["variance"]
        self.save(update_fields=["total_sales", "total_variance"])
        return res


class CashUpLine(models.Model):
    cashup = models.ForeignKey(CashUp, on_delete=models.CASCADE, related_name="lines")
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="+")
    till_amount = models.DecimalField("Till says", max_digits=12, decimal_places=2, default=Z)
    actual_amount = models.DecimalField("Really received", max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["cashup", "method__sort_order", "method__name"]


class Expense(models.Model):
    TILL, BANK, OWNER = "till", "bank", "owner"
    PAID_FROM = [(TILL, "Cash out of the till"), (BANK, "Bank / card / EcoCash"), (OWNER, "Owner paid (own pocket)")]

    date = models.DateField()
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    payee = models.CharField("Paid to", max_length=100, blank=True)
    description = models.CharField("What for", max_length=200, blank=True)
    amount = models.DecimalField("Amount ($)", max_digits=12, decimal_places=2)
    vat = models.DecimalField("VAT on the receipt ($)", max_digits=12, decimal_places=2, default=Z,
                              help_text="Only if you are VAT registered and the receipt shows VAT")
    paid_from = models.CharField("Paid from", max_length=6, choices=PAID_FROM, default=BANK)
    receipt_no = models.CharField("Receipt / slip no.", max_length=60, blank=True)
    account = models.ForeignKey("money.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses",
                                verbose_name="Which account", help_text="Only when paid from the bank / EcoCash (empty = the bank)")
    cashup = models.ForeignKey(CashUp, null=True, blank=True, on_delete=models.CASCADE, related_name="expenses",
                               help_text="Set when the money came out of the till during a cash-up")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date:%d %b %Y} {self.category} {self.amount}"

    @property
    def amount_excl(self):
        return self.amount - (self.vat or Z)


class DaySales(models.Model):
    """Products sold on one day (all tills together), typed from the till's product report."""

    date = models.DateField(unique=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "day sales"

    def __str__(self):
        return f"Product sales {self.date:%d %b %Y}"

    @property
    def number(self):
        return f"S-{self.pk:04d}"

    def totals(self):
        lines = list(self.lines.all())
        t = {
            "qty": sum((ln.qty for ln in lines), Z),
            "value": sum((ln.value for ln in lines), Z),
            "excl": sum((ln.value_excl for ln in lines), Z),
            "cost": sum((ln.cost for ln in lines), Z),
        }
        t["gp"] = (t["excl"] - t["cost"]) / t["excl"] if t["excl"] else None
        return t


class SaleLine(models.Model):
    day = models.ForeignKey(DaySales, on_delete=models.CASCADE, related_name="lines")
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField("Price each incl. VAT", max_digits=10, decimal_places=2, default=Z)
    vat_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Z)
    unit_cost = models.DecimalField("Cost each when sold", max_digits=12, decimal_places=4, default=Z)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["day", "position", "id"]

    @property
    def value(self):
        return (self.qty * self.price).quantize(C)

    @property
    def value_excl(self):
        return self.qty * self.price / (1 + self.vat_rate)

    @property
    def cost(self):
        return self.qty * self.unit_cost

    @property
    def gp(self):
        v = self.value_excl
        return None if not v else (v - self.cost) / v


class DailySales(models.Model):
    """The day's sales per category (excl. VAT), from the till report – like the Excel 'Daily Sales' sheet.
    This is what the dashboard counts as sales."""

    date = models.DateField(unique=True)
    gp = models.DecimalField("GP % of the day (from the till)", max_digits=6, decimal_places=4, null=True,
                             blank=True, help_text="Leave empty to use the GP of your recipes")
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    gp_amount = models.DecimalField("Gross profit ($)", max_digits=12, decimal_places=2, default=Z)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name_plural = "daily sales"

    def __str__(self):
        return f"Sales {self.date:%d %b %Y}"

    @property
    def gp_pct(self):
        return (self.gp_amount / self.total) if self.total else None


class DailySalesLine(models.Model):
    day = models.ForeignKey(DailySales, on_delete=models.CASCADE, related_name="lines")
    category = models.ForeignKey("costing.Category", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField("Sales excl. VAT ($)", max_digits=12, decimal_places=2)
    gp = models.DecimalField("GP used", max_digits=6, decimal_places=4, default=Z)

    class Meta:
        ordering = ["day", "category__sort_order", "category__name"]
