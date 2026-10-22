from decimal import ROUND_CEILING, Decimal

from django.conf import settings
from django.db import models

from costing.models import Recipe

SHIFTS = [("day", "Day shift"), ("night", "Night shift")]


class ProductionPlan(models.Model):
    DRAFT, FINAL, DONE = "draft", "final", "done"
    STATUS = [(DRAFT, "Draft"), (FINAL, "Final – give to bakers"), (DONE, "Done")]

    date = models.DateField()
    shift = models.CharField(max_length=6, choices=SHIFTS, default="day")
    status = models.CharField(max_length=6, choices=STATUS, default=DRAFT)
    planned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    supervisor = models.CharField("Supervisor on shift", max_length=80, blank=True)
    notes = models.TextField("Notes for the bakers", blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "shift"]
        constraints = [models.UniqueConstraint(fields=["date", "shift"], name="one_plan_per_shift")]

    def __str__(self):
        return f"{self.date:%a %d %b %Y} – {self.get_shift_display()}"

    @property
    def number(self):
        return f"P-{self.pk:04d}"


class PlanLine(models.Model):
    plan = models.ForeignKey(ProductionPlan, on_delete=models.CASCADE, related_name="lines")
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, related_name="+")
    model_stock = models.PositiveIntegerField("Model stock", default=0)
    on_hand = models.PositiveIntegerField("On hand", default=0)
    expired = models.PositiveIntegerField("Expired / removed", default=0)
    actual = models.PositiveIntegerField("Make (your number)", null=True, blank=True,
                                         help_text="Leave empty to make the suggested amount")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["plan", "position", "id"]

    @property
    def available(self):
        return max(0, self.on_hand - self.expired)

    @property
    def suggested(self):
        return max(0, self.model_stock - self.available)

    @property
    def units(self):
        return self.actual if self.actual is not None else self.suggested


WASTE_REASONS = ["Expired", "Damaged", "Over-production", "Burnt / quality", "Customer return", "Staff / tasting", "Other"]


class WasteLog(models.Model):
    date = models.DateField()
    shift = models.CharField(max_length=6, choices=SHIFTS, default="day")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    notes = models.TextField(blank=True)
    signed_off_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="+")
    signed_off_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "shift"]
        constraints = [models.UniqueConstraint(fields=["date", "shift"], name="one_waste_log_per_shift")]

    def __str__(self):
        return f"Waste {self.date:%d %b %Y} – {self.get_shift_display()}"

    @property
    def number(self):
        return f"W-{self.pk:04d}"

    @property
    def total_cost(self):
        return sum((ln.line_cost for ln in self.lines.all()), Decimal("0"))


class WasteLine(models.Model):
    log = models.ForeignKey(WasteLog, on_delete=models.CASCADE, related_name="lines")
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=30, default="Expired")
    notes = models.CharField(max_length=200, blank=True)
    unit_cost = models.DecimalField("Cost per unit when logged", max_digits=12, decimal_places=4, default=Decimal("0"))

    class Meta:
        ordering = ["log", "id"]

    @property
    def line_cost(self):
        return (self.qty * self.unit_cost).quantize(Decimal("0.01"))


class PlanUsage(models.Model):
    """Ingredients a finished (Done) plan took out of the store."""

    plan = models.ForeignKey(ProductionPlan, on_delete=models.CASCADE, related_name="usage")
    ingredient = models.ForeignKey("costing.Ingredient", on_delete=models.CASCADE, related_name="+")
    qty = models.DecimalField(max_digits=14, decimal_places=4)
