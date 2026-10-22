"""Equipment register, monthly count and straight-line depreciation (the Excel 'Equipment' sheets)."""
import datetime
from decimal import Decimal

from django.conf import settings
from django.db import models

Z = Decimal("0")


def month_index(d):
    return d.year * 12 + d.month - 1


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    life_years = models.DecimalField("Default useful life (years)", max_digits=5, decimal_places=1, default=Decimal("5"))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "equipment categories"

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=80, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    asset_no = models.CharField("Asset no.", max_length=20, unique=True, help_text="Write it on the item too, e.g. EQ-144")
    description = models.CharField("Item", max_length=200)
    category = models.ForeignKey(EquipmentCategory, on_delete=models.PROTECT, related_name="items")
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    serial = models.CharField("Serial / model no.", max_length=80, blank=True)
    supplier = models.CharField(max_length=120, blank=True)
    purchase_date = models.DateField(default=datetime.date.today)
    unit_cost = models.DecimalField("Cost each ($ excl. VAT)", max_digits=12, decimal_places=2)
    qty = models.PositiveIntegerField("Qty bought", default=1)
    life_override = models.DecimalField("Useful life (years) – only if not the category's", max_digits=5,
                                        decimal_places=1, null=True, blank=True)
    scrap_value = models.DecimalField("Scrap value at the end ($)", max_digits=12, decimal_places=2, default=Z)
    disposed_on = models.DateField("Sold / scrapped / written off on", null=True, blank=True)
    disposed_note = models.CharField("What happened", max_length=150, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["asset_no"]

    def __str__(self):
        return f"{self.asset_no} {self.description}"

    @property
    def total_cost(self):
        return self.unit_cost * self.qty

    @property
    def life(self):
        return self.life_override if self.life_override else self.category.life_years

    @property
    def life_months(self):
        return int(self.life * 12)

    @property
    def per_month(self):
        m = self.life_months
        return ((self.total_cost - self.scrap_value) / m) if m else Z

    def months_until(self, month):
        """How many months are depreciated up to and including 'month' (the purchase month counts as month 1)."""
        start = month_index(self.purchase_date)
        end = month_index(month)
        if self.disposed_on:
            end = min(end, month_index(self.disposed_on))
        return max(0, min(self.life_months, end - start + 1))

    def dep_in(self, month):
        """Depreciation for one month."""
        return self.per_month if self.months_until(month) > self.months_until(_prev(month)) else Z

    def dep_to(self, month):
        return self.per_month * self.months_until(month)

    def book_value(self, month):
        if self.disposed_on and month_index(self.disposed_on) <= month_index(month):
            return Z
        return max(self.scrap_value, self.total_cost - self.dep_to(month))

    def expected_qty(self, month):
        if self.disposed_on and month_index(self.disposed_on) <= month_index(month):
            return 0
        if month_index(self.purchase_date) > month_index(month):
            return 0
        return self.qty


def _prev(month):
    return (month.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)


class EquipmentCount(models.Model):
    month = models.DateField(unique=True, help_text="The 1st of the month counted")
    date = models.DateField("Count date", default=datetime.date.today)
    counted_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"Equipment count {self.month:%B %Y}"


class CountLine(models.Model):
    count = models.ForeignKey(EquipmentCount, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="counts")
    qty = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["count", "item"], name="one_line_per_item_per_count")]
