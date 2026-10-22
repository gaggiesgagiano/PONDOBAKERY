"""Money & accounts.

* Account        – where money is kept: the safe (cash), the bank, EcoCash. Each has a starting balance.
* Entry          – money moved by hand: the owner / boss putting money in, loans, drawings, ZIMRA / NSSA payments,
                   bank charges, banking the safe cash (a move between two accounts) …
* SupplierPayment – paying a supplier, split over that supplier's GRVs (invoices) – what we still owe is what is not paid.
* BankCheck      – the balance on the bank (or EcoCash) statement on a day, compared with what Pondo says.

Everything else in the cash book comes in by itself: cash-ups (cash to the safe, swipe to the bank, EcoCash),
expenses paid from the bank, wages, staff advances and customer invoices that were paid.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

Z = Decimal("0")


class Account(models.Model):
    SAFE, BANK, MOBILE = "safe", "bank", "mobile"
    KINDS = [(SAFE, "Cash in the safe"), (BANK, "Bank account"), (MOBILE, "EcoCash / mobile money")]

    name = models.CharField(max_length=60, unique=True)
    kind = models.CharField(max_length=6, choices=KINDS, default=BANK)
    number = models.CharField("Account no. (last 4 digits are enough)", max_length=40, blank=True)
    opening_date = models.DateField("Start date", help_text="The day Pondo starts keeping this account's book")
    opening_balance = models.DecimalField("Balance on the start date ($)", max_digits=14, decimal_places=2, default=Z,
                                          help_text="What was in the account at the start of that day")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Entry(models.Model):
    """Money moved by hand (everything that does not come in by itself)."""
    OWNER_IN, LOAN_IN, LOAN_REPAY, DRAWINGS = "owner_in", "loan_in", "loan_repay", "drawings"
    CUSTOMER, OTHER_IN, INTEREST = "customer", "other_in", "interest"
    PAYE, VAT, TAX, NSSA, ZIMDEF = "paye", "vat", "tax", "nssa", "zimdef"
    CHARGES, ASSET, OTHER_OUT, TRANSFER = "charges", "asset", "other_out", "transfer"
    KINDS = [
        ("Money in", [(OWNER_IN, "Owner / boss put money in (capital)"),
                      (LOAN_IN, "Loan to the business (owner, boss or bank)"),
                      (CUSTOMER, "Customer paid (not on a Pondo invoice)"),
                      (INTEREST, "Interest received"),
                      (OTHER_IN, "Other money in")]),
        ("Money out", [(LOAN_REPAY, "Loan paid back"),
                       (DRAWINGS, "Owner took money out (drawings)"),
                       (PAYE, "Paid ZIMRA – PAYE & AIDS levy"),
                       (VAT, "Paid ZIMRA – VAT"),
                       (TAX, "Paid ZIMRA – income tax / other tax"),
                       (NSSA, "Paid NSSA"),
                       (ZIMDEF, "Paid ZIMDEF"),
                       (CHARGES, "Bank / EcoCash charges"),
                       (ASSET, "Bought equipment / building work"),
                       (OTHER_OUT, "Other money out")]),
        ("Between accounts", [(TRANSFER, "Move money between accounts (e.g. safe cash taken to the bank)")]),
    ]
    IN_KINDS = {OWNER_IN, LOAN_IN, CUSTOMER, INTEREST, OTHER_IN}

    date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="entries",
                                help_text="For a move: the account the money comes OUT of")
    kind = models.CharField("What happened", max_length=10, choices=KINDS)
    to_account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="entries_in",
                                   verbose_name="To account", help_text="Only for a move between accounts")
    amount = models.DecimalField("Amount ($)", max_digits=14, decimal_places=2)
    description = models.CharField("Details", max_length=200, blank=True)
    ref = models.CharField("Ref / slip no.", max_length=60, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "entries"

    def __str__(self):
        return f"{self.date:%d %b %Y} {self.get_kind_display()} {self.amount}"

    @property
    def is_in(self):
        return self.kind in self.IN_KINDS


class SupplierPayment(models.Model):
    supplier = models.ForeignKey("costing.Supplier", on_delete=models.PROTECT, related_name="payments")
    date = models.DateField()
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.PROTECT, related_name="supplier_payments",
                                help_text="Empty = the owner / boss paid from his own pocket")
    amount = models.DecimalField("Amount paid ($)", max_digits=14, decimal_places=2)
    ref = models.CharField("Ref / proof of payment no.", max_length=60, blank=True)
    notes = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Payment {self.number} {self.supplier} {self.amount}"

    @property
    def number(self):
        return f"SP-{self.pk:04d}"

    @property
    def allocated(self):
        return sum((a.amount for a in self.allocations.all()), Z)


class Allocation(models.Model):
    """Which supplier invoice (GRV) a payment pays, and how much of it."""
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, related_name="allocations")
    grv = models.ForeignKey("stock.GRV", on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["grv__date", "id"]


class BankCheck(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="checks")
    date = models.DateField("Statement date")
    statement_balance = models.DecimalField("Balance on the statement ($)", max_digits=14, decimal_places=2)
    pondo_balance = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField("Why it differs / what was done", blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    @property
    def difference(self):
        return self.statement_balance - self.pondo_balance
