"""Quotations, pro-forma invoices and tax invoices for customers (the Excel 'Invoice' sheets)."""
import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from costing.models import Recipe
from staff.storage import staff_storage

Z = Decimal("0")
C = Decimal("0.01")


class Customer(models.Model):
    name = models.CharField("Name", max_length=120)
    company = models.CharField(max_length=150, blank=True)
    address1 = models.CharField("Address", max_length=150, blank=True)
    address2 = models.CharField("Address line 2 / town", max_length=150, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    email = models.CharField(max_length=120, blank=True)
    vat_no = models.CharField("VAT no.", max_length=60, blank=True)
    tin = models.CharField("TIN no.", max_length=20, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.company})" if self.company else self.name


class Document(models.Model):
    QUOTE, PROFORMA, INVOICE = "quote", "proforma", "invoice"
    KINDS = [(QUOTE, "Quotation"), (PROFORMA, "Pro-forma invoice"), (INVOICE, "Tax invoice")]
    PREFIX = {QUOTE: "QT", PROFORMA: "PF", INVOICE: "INV"}
    OPEN, ACCEPTED, PAID, CANCELLED = "open", "accepted", "paid", "cancelled"
    STATUS = [(OPEN, "Open"), (ACCEPTED, "Accepted"), (PAID, "Paid"), (CANCELLED, "Cancelled")]

    kind = models.CharField("Document type", max_length=10, choices=KINDS, default=INVOICE)
    seq = models.PositiveIntegerField(default=0)
    date = models.DateField(default=datetime.date.today)
    due = models.DateField("Due date / valid until", null=True, blank=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    # copied from the customer when saved, so old documents never change
    name = models.CharField("Name", max_length=120)
    company = models.CharField(max_length=150, blank=True)
    address1 = models.CharField("Address", max_length=150, blank=True)
    address2 = models.CharField("Address line 2 / town", max_length=150, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    email = models.CharField(max_length=120, blank=True)
    vat_no = models.CharField("Customer VAT no.", max_length=60, blank=True)
    your_ref = models.CharField("Your ref / order no.", max_length=80, blank=True)
    prepared_by = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default=OPEN)
    paid_on = models.DateField(null=True, blank=True)
    paid_how = models.CharField("Paid how", max_length=60, blank=True)
    from_doc = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    subtotal = models.DecimalField("Subtotal excl. VAT", max_digits=12, decimal_places=2, default=Z)
    vat = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    total = models.DecimalField("Total incl. VAT", max_digits=12, decimal_places=2, default=Z)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [models.UniqueConstraint(fields=["kind", "seq"], name="one_number_per_document_type")]

    def __str__(self):
        return f"{self.number} {self.name}"

    @property
    def number(self):
        return f"{self.PREFIX[self.kind]}-{self.seq}"

    @property
    def title(self):
        return {self.QUOTE: "QUOTATION", self.PROFORMA: "PRO-FORMA INVOICE", self.INVOICE: "TAX INVOICE"}[self.kind]

    @property
    def overdue(self):
        return (self.kind == self.INVOICE and self.status == self.OPEN and self.due
                and self.due < datetime.date.today())

    def save(self, *a, **kw):
        if not self.seq:
            last = Document.objects.filter(kind=self.kind).aggregate(m=models.Max("seq"))["m"]
            self.seq = (last or 1000) + 1
        super().save(*a, **kw)

    def refresh_totals(self):
        lines = list(self.lines.all())
        self.total = sum((ln.total for ln in lines), Z)
        self.subtotal = sum((ln.total_excl for ln in lines), Z).quantize(C, rounding=ROUND_HALF_UP)
        self.vat = self.total - self.subtotal
        self.save(update_fields=["total", "subtotal", "vat"])


class DocLine(models.Model):
    doc = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="lines")
    recipe = models.ForeignKey(Recipe, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    description = models.CharField(max_length=200)
    qty = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField("Unit price incl. VAT", max_digits=10, decimal_places=2)
    discount = models.DecimalField("Discount", max_digits=6, decimal_places=4, default=Z, help_text="0.10 = 10%")
    vat_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Z)
    position = models.PositiveIntegerField(default=0)
    is_fee = models.BooleanField("Delivery fee for the driver", default=False)

    class Meta:
        ordering = ["doc", "position", "id"]

    @property
    def total(self):
        return (self.qty * self.price * (1 - self.discount)).quantize(C, rounding=ROUND_HALF_UP)

    @property
    def total_excl(self):
        return self.total / (1 + self.vat_rate)


def driver_photo_path(instance, filename):
    import os
    import uuid

    ext = os.path.splitext(filename)[1].lower()[:8] or ".jpg"
    return f"drivers/{instance.pk}/{getattr(instance, '_which', 'photo')}-{uuid.uuid4().hex[:8]}{ext}"


class Driver(models.Model):
    """A delivery driver (usually from inDrive) the bakery has checked: photo, ID, cell and car. Gets an ID card."""

    name = models.CharField("Name and surname", max_length=80)
    phone = models.CharField("Cell", max_length=40, blank=True)
    id_number = models.CharField("National ID no.", max_length=40, blank=True)
    licence_no = models.CharField("Driver's licence no.", max_length=40, blank=True)
    car_reg = models.CharField("Car registration", max_length=20, blank=True)
    car_make = models.CharField("Make / model", max_length=60, blank=True, help_text="e.g. Honda Fit")
    car_colour = models.CharField("Colour", max_length=30, blank=True)
    photo = models.FileField(storage=staff_storage, upload_to=driver_photo_path, blank=True, max_length=200)
    car_photo = models.FileField(storage=staff_storage, upload_to=driver_photo_path, blank=True, max_length=200)
    issued = models.DateField("ID card issued", default=datetime.date.today)
    active = models.BooleanField("May deliver for us", default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active", "name"]

    def __str__(self):
        return self.name

    @property
    def number(self):
        return f"DRV-{self.pk or 0:03d}"

    @property
    def car(self):
        return " ".join(x for x in (self.car_colour, self.car_make) if x)

    @property
    def first(self):
        return (self.name.split() or [""])[0]

    @property
    def initials(self):
        w = self.name.split()
        return ((w[0][0] + w[-1][0]) if len(w) > 1 else self.name[:2]).upper() or "?"

    @property
    def photo_v(self):
        return int(self.updated_at.timestamp()) if self.updated_at else 0


@receiver(post_delete, sender=Driver)
def _remove_driver_photos(sender, instance, **kw):
    for f in (instance.photo, instance.car_photo):
        if f:
            try:
                f.storage.delete(f.name)
            except OSError:
                pass


class Delivery(models.Model):
    """An order sent to a customer with a driver (usually inDrive).

    The customer gets a tax invoice for the goods + the driver's delivery fee. The driver collects the money, keeps
    the fee and brings back the money for the goods, which is rung up on the till. Then the delivery is checked off.
    """

    DRIVER, ECOCASH, SWIPE, BANK, ACCOUNT = "driver", "ecocash", "swipe", "bank", "account"
    PAY = [(DRIVER, "Cash to the driver – the driver keeps the fee and brings back the rest"),
           (ECOCASH, "EcoCash to the bakery"), (SWIPE, "Swipe / card at the bakery"),
           (BANK, "Bank transfer to the bakery"), (ACCOUNT, "On account – the customer pays the invoice later")]
    PAY_SHORT = {DRIVER: "Cash via the driver", ECOCASH: "EcoCash", SWIPE: "Swipe / card", BANK: "Bank transfer",
                 ACCOUNT: "On account"}
    OUT, DONE, CANCELLED = "out", "done", "cancelled"
    STATUS = [(OUT, "Out with the driver"), (DONE, "Done"), (CANCELLED, "Cancelled")]

    doc = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="delivery")
    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries")
    date = models.DateField(default=datetime.date.today)
    sent_at = models.DateTimeField("Left the bakery", default=timezone.now)
    directions = models.CharField("Directions / landmark", max_length=200, blank=True)
    driver_name = models.CharField("Driver's name", max_length=80)
    driver_phone = models.CharField("Driver's cell", max_length=40, blank=True)
    car_reg = models.CharField("Car registration", max_length=20)
    car_make = models.CharField("Make / model", max_length=60, blank=True, help_text="e.g. Honda Fit")
    car_colour = models.CharField("Colour", max_length=30, blank=True)
    fee = models.DecimalField("Delivery fee ($)", max_digits=8, decimal_places=2, default=Z,
                              help_text="What the inDrive driver asked. The driver keeps it.")
    goods = models.DecimalField("Goods incl. VAT ($)", max_digits=12, decimal_places=2, default=Z)
    pay = models.CharField("The customer pays", max_length=8, choices=PAY, default=DRIVER)
    status = models.CharField(max_length=10, choices=STATUS, default=OUT)
    delivered_at = models.DateTimeField(null=True, blank=True)
    money_back = models.DecimalField("Money the driver brought back ($)", max_digits=12, decimal_places=2,
                                     null=True, blank=True)
    rung_up = models.DecimalField("Rung up on the till ($)", max_digits=12, decimal_places=2, null=True, blank=True)
    till_ref = models.CharField("Till slip / receipt no.", max_length=40, blank=True)
    back_note = models.CharField("Note", max_length=200, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-sent_at", "-id"]
        verbose_name_plural = "deliveries"

    def __str__(self):
        return f"{self.number} {self.doc.name}"

    @property
    def number(self):
        return f"DEL-{self.pk or 0:04d}"

    @property
    def total(self):
        """What the customer pays: goods + the driver's fee."""
        return self.goods + self.fee

    @property
    def pay_short(self):
        return self.PAY_SHORT.get(self.pay, "")

    @property
    def by_driver(self):
        return self.pay == self.DRIVER

    @property
    def collect(self):
        """Money the driver collects from the customer."""
        return self.total if self.by_driver else Z

    @property
    def expected_back(self):
        return self.goods if self.by_driver else Z

    @property
    def difference(self):
        """+ over, − short (only when the driver brought money back)."""
        if not self.by_driver or self.money_back is None:
            return None
        return self.money_back - self.expected_back

    @property
    def car(self):
        return " ".join(x for x in (self.car_colour, self.car_make) if x)

    @property
    def stage(self):
        if self.status == self.CANCELLED:
            return "cancelled"
        if self.status == self.DONE:
            return "done"
        return "delivered" if self.delivered_at else "out"
