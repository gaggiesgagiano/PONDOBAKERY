"""ZIMRA fiscalisation settings and the journal of every call to the fiscal engine."""
from django.conf import settings
from django.db import models


class FiscalSetup(models.Model):
    """One row: is the till fiscalising, and against which ZIMRA server."""
    OFF, TEST, LIVE = "off", "test", "live"
    MODES = [(OFF, "Off – practice slips (not tax invoices)"),
             (TEST, "ZIMRA TEST – practice with ZIMRA's test server"),
             (LIVE, "LIVE – real ZIMRA fiscal tax invoices")]

    mode = models.CharField(max_length=4, choices=MODES, default=OFF)
    hs_code = models.CharField("HS code for bakery products", max_length=8, blank=True,
                               help_text="ZIMRA wants a customs (HS) code on every line. Ask your accountant – "
                                         "bakery goods are usually under 1905. Empty = 00000000.")
    auto_open_day = models.BooleanField("Open the fiscal day by itself at the first sale", default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")

    class Meta:
        verbose_name = "fiscal setup"

    def __str__(self):
        return self.get_mode_display()

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        return obj if obj is not None else cls.objects.create()

    @property
    def active(self):
        return self.mode in (self.TEST, self.LIVE)


class FiscalCall(models.Model):
    """Every call to the engine and its answer – the first place to look when ZIMRA says no."""
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    method = models.CharField(max_length=60)
    ok = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    data = models.TextField(blank=True)
    seconds = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    sale = models.ForeignKey("till.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="fiscal_calls")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.at:%d %b %H:%M} {self.method}"
