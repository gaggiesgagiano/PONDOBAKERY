"""The Pondo till (point of sale).

* Till     – Till 1, Till 2 …
* Shift    – one till, one cashier, one day: the float, the ZiG rate, opened and closed.
             Closing a shift makes the normal cash-up, so the rest of Pondo works as before.
* Sale     – one receipt. A refund is a Sale with kind = refund and negative amounts.
* SaleItem / SalePayment – the products and how it was paid (split payments allowed).

Fiscal fields hold the ZIMRA receipt (fiscal/service.py). While fiscalisation is Off every receipt is a practice receipt.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models

Z = Decimal("0")
C = Decimal("0.01")


def zwg_price(usd_price, rate):
    """A US$ price in ZWG: rounded to the cent. The till screen, the slip and ZIMRA all use this same rule."""
    return (Decimal(usd_price) * Decimal(rate)).quantize(C, ROUND_HALF_UP)


def zwg_line(usd_price, qty, rate):
    return (zwg_price(usd_price, rate) * Decimal(qty)).quantize(C, ROUND_HALF_UP)


class Till(models.Model):
    name = models.CharField(max_length=40, unique=True)
    code = models.CharField("Short code on receipts", max_length=6, unique=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Shift(models.Model):
    """One cashier on one till – a till can have several shifts a day (re-opened for the next shift)."""
    till = models.ForeignKey(Till, on_delete=models.PROTECT, related_name="shifts")
    date = models.DateField()
    number = models.PositiveSmallIntegerField("Shift of the day", default=1)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    opening_float = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    float_checked_by = models.CharField("Float counted with", max_length=80, blank=True)
    zig_rate = models.DecimalField("ZiG per US$1", max_digits=10, decimal_places=4, null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    cashup = models.OneToOneField("sales.CashUp", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="till_shift")

    class Meta:
        ordering = ["-date", "till__sort_order", "-number"]
        constraints = [models.UniqueConstraint(fields=["till", "date", "number"], name="shift_number_per_till_per_day")]

    def __str__(self):
        return f"{self.label} {self.date:%d %b %Y}"

    @property
    def label(self):
        return self.till.name if self.number == 1 else f"{self.till.name} #{self.number}"

    @property
    def is_open(self):
        return self.closed_at is None

    def cashier_name(self):
        u = self.cashier
        return (f"{u.first_name} {u.last_name}".strip() or u.username)


class Sale(models.Model):
    SALE, REFUND = "sale", "refund"
    KINDS = [(SALE, "Sale"), (REFUND, "Refund")]

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="sales")
    number = models.CharField(max_length=20, unique=True)
    kind = models.CharField(max_length=8, choices=KINDS, default=SALE)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    vat = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    refund_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reason = models.CharField(max_length=200, blank=True)
    # currency of the receipt: USD, or ZWG when the customer paid everything in ZWG. total/vat/change above stay in
    # US$ (the books); the *_fx fields are the same amounts in ZWG at fx_rate, as printed and sent to ZIMRA.
    currency = models.CharField(max_length=3, default="USD")
    fx_rate = models.DecimalField("ZWG per US$1", max_digits=10, decimal_places=4, null=True, blank=True)
    total_fx = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    vat_fx = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    change_fx = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # the customer, only when they ask for their details on the slip (also sent to ZIMRA)
    customer = models.ForeignKey("invoices.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="till_sales")
    customer_name = models.CharField("Name & surname or business name", max_length=150, blank=True)
    customer_tin = models.CharField("TIN no.", max_length=20, blank=True)
    customer_vat = models.CharField("VAT no.", max_length=20, blank=True)
    customer_address = models.CharField("Address", max_length=250, blank=True)
    customer_email = models.CharField("E-mail", max_length=120, blank=True)
    customer_phone = models.CharField("Phone", max_length=40, blank=True)
    # ZIMRA fiscal receipt (see fiscal/service.py): practice · submitted · pending · failed
    fiscal_status = models.CharField(max_length=20, default="practice")
    fiscal_ref = models.CharField("Invoice number sent to ZIMRA", max_length=80, blank=True, db_index=True)
    fiscal_mode = models.CharField(max_length=4, blank=True)          # test / live when it was fiscalised
    fiscal_qr = models.CharField("ZIMRA QR link", max_length=300, blank=True)
    fiscal_day = models.CharField(max_length=20, blank=True)
    fiscal_global_no = models.CharField(max_length=20, blank=True)
    fiscal_device = models.CharField(max_length=20, blank=True)
    fiscal_message = models.TextField(blank=True)
    fiscal_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.number

    @property
    def is_refund(self):
        return self.kind == self.REFUND

    @property
    def in_zwg(self):
        return self.currency == "ZWG" and bool(self.fx_rate)

    def lines(self):
        """[(item, price, line total)] in the receipt's currency."""
        out = []
        for it in self.items.all():
            if self.in_zwg:
                out.append((it, zwg_price(it.price, self.fx_rate), zwg_line(it.price, it.qty, self.fx_rate)))
            else:
                out.append((it, it.price, it.total))
        return out

    @property
    def is_fiscal(self):
        """A real (or ZIMRA-test) fiscal receipt with its QR code."""
        return self.fiscal_status in ("submitted", "pending", "flagged") and bool(self.fiscal_qr)

    def refunded_qty(self):
        """{recipe_id: qty already refunded} for this sale."""
        out = {}
        for r in self.refunds.all():
            for it in r.items.all():
                out[it.recipe_id] = out.get(it.recipe_id, Z) + (-it.qty)
        return out


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    recipe = models.ForeignKey("costing.Recipe", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=150)
    qty = models.DecimalField(max_digits=10, decimal_places=3)
    price = models.DecimalField("Price each incl. VAT", max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=6, decimal_places=4, default=Z)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=Z)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["sale", "id"]

    @property
    def total_excl(self):
        return self.total / (1 + self.vat_rate)


class SalePayment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.ForeignKey("sales.PaymentMethod", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField("Amount ($)", max_digits=12, decimal_places=2)
    tendered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    zig_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    zig_rate = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    ref = models.CharField("Reference", max_length=80, blank=True)

    class Meta:
        ordering = ["sale", "id"]

    @property
    def label(self):
        """'USD Cash', 'ZWG EcoCash' … – the currency it was paid in, then how."""
        name = self.method.name.replace("(US$)", "").replace("(USD)", "").strip()
        low = name.lower()
        short = ("Cash" if self.method.is_cash else "Card" if ("card" in low or "swipe" in low)
                 else "EcoCash" if "ecocash" in low else "Bank transfer" if "bank" in low else name)
        return ("ZWG " if self.zig_amount else "USD ") + short


class TillMovement(models.Model):
    """Cash drop to the safe, money paid out of the till, or the drawer opened without a sale – always approved."""
    DROP, PAYOUT, NOSALE = "drop", "payout", "nosale"
    KINDS = [(DROP, "Cash drop to the safe"), (PAYOUT, "Paid out of the till"), (NOSALE, "No sale – drawer opened")]

    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=8, choices=KINDS)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Z)
    reason = models.CharField(max_length=200, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expense = models.OneToOneField("sales.Expense", null=True, blank=True, on_delete=models.SET_NULL, related_name="till_movement")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount}"

    @property
    def number(self):
        return f"{self.shift.till.code}-M{self.pk:04d}"
