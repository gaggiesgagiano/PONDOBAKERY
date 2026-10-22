import json

from django.conf import settings
from django.db import models


class MonthClose(models.Model):
    """A month whose final figures are locked (the Excel 'Month Archive')."""

    month = models.DateField(unique=True, help_text="The 1st of the month")
    figures_json = models.TextField(default="{}")
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+")
    locked_at = models.DateTimeField(auto_now_add=True)
    sent_to_accountant = models.CharField("Sent to accountant (date / initials)", max_length=80, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"{self.month:%B %Y}"

    @property
    def figures(self):
        return json.loads(self.figures_json or "{}")
