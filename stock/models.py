from decimal import Decimal

from django.conf import settings
from django.db import models

from costing.models import Ingredient, Recipe, Supplier

Z = Decimal("0")


class PurchaseOrder(models.Model):
    DRAFT, SENT, RECEIVED, CANCELLED = "draft", "sent", "received", "cancelled"
    STATUS = [(DRAFT, "Draft"), (SENT, "Sent to supplier"), (RECEIVED, "Received"), (CANCELLED, "Cancelled")]

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    date = models.DateField("Order date")
    delivery_date = models.DateField("Delivery date", null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=DRAFT)
    ordered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField("Notes / delivery instructions", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} {self.supplier}"

    @property
    def number(self):
        return f"PO-{1000 + self.pk}"

    @property
    def total(self):
        return sum((ln.line_total for ln in self.lines.all()), Z)


class OrderSend(models.Model):
    """Every time an order went to the supplier: how, to whom, by whom and when."""
    EMAIL, WHATSAPP = "email", "whatsapp"
    HOW = [(EMAIL, "E-mail"), (WHATSAPP, "WhatsApp")]

    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="sends")
    how = models.CharField(max_length=10, choices=HOW)
    to = models.CharField("Sent to", max_length=300)
    when = models.DateTimeField(auto_now_add=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ok = models.BooleanField(default=True)
    details = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-when", "-id"]

    def __str__(self):
        return f"{self.order.number} {self.get_how_display()} {self.to}"


class OrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="+")
    packs = models.DecimalField(max_digits=10, decimal_places=2)
    pack_price = models.DecimalField(max_digits=12, decimal_places=4, default=Z)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "position", "id"]

    @property
    def line_total(self):
        return self.packs * self.pack_price


class GRV(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="grvs")
    order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="grvs")
    date = models.DateField("Date received")
    invoice_no = models.CharField("Supplier invoice no.", max_length=60, blank=True)
    invoice_total = models.DecimalField("Invoice total ($)", max_digits=12, decimal_places=2, null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField("Notes / problems", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "GRV"

    def __str__(self):
        return f"{self.number} {self.supplier}"

    @property
    def number(self):
        return f"GRV-{self.pk:04d}"

    @property
    def total(self):
        return sum((ln.line_total for ln in self.lines.all()), Z)

    @property
    def total_excl(self):
        return sum((ln.value_excl for ln in self.lines.all()), Z)


class GRVLine(models.Model):
    grv = models.ForeignKey(GRV, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="+")
    packs_ordered = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    packs = models.DecimalField("Packs received", max_digits=10, decimal_places=2)
    pack_price = models.DecimalField(max_digits=12, decimal_places=4)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["grv", "position", "id"]

    @property
    def line_total(self):
        return self.packs * self.pack_price

    @property
    def value_excl(self):
        return self.line_total / (1 + (self.ingredient.vat_rate or Z))

    @property
    def units(self):
        return self.packs * self.ingredient.pack_size

    @property
    def short(self):
        if self.packs_ordered is None:
            return None
        return self.packs - self.packs_ordered


class StockCount(models.Model):
    DRAFT, FINAL = "draft", "final"
    date = models.DateField("Count date")
    counted_by = models.CharField(max_length=80, blank=True)
    checked_by = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=6, choices=[(DRAFT, "Busy counting"), (FINAL, "Final")], default=DRAFT)
    notes = models.TextField(blank=True)
    total_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    as_at = models.DateTimeField("Stock as at", null=True, blank=True, help_text="When counting started – expected stock is worked out to this moment")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Stock take {self.date:%d %b %Y}"

    @property
    def number(self):
        return f"ST-{self.pk:04d}"


class CountLine(models.Model):
    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="lines")
    ingredient = models.ForeignKey(Ingredient, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    recipe = models.ForeignKey(Recipe, null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                               help_text="Finished products on the shop floor")
    qty = models.DecimalField(max_digits=14, decimal_places=3)
    expected = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=Z)
    reason = models.TextField("Why short / over", blank=True)

    @property
    def value(self):
        return self.qty * self.unit_cost
