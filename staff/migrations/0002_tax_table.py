from decimal import Decimal as D

from django.db import migrations

# ZIMRA monthly USD PAYE table, 1 January – 31 December 2025 (latest published by ZIMRA)
BANDS = [(D("100"), D("0"), D("0")), (D("300"), D("0.20"), D("20")), (D("1000"), D("0.25"), D("35")),
         (D("2000"), D("0.30"), D("85")), (D("3000"), D("0.35"), D("185")), (None, D("0.40"), D("335"))]


def add(apps, schema_editor):
    PayeBand = apps.get_model("staff", "PayeBand")
    PayrollSettings = apps.get_model("staff", "PayrollSettings")
    if not PayeBand.objects.exists():
        for up_to, rate, deduct in BANDS:
            PayeBand.objects.create(up_to=up_to, rate=rate, deduct=deduct)
    if not PayrollSettings.objects.exists():
        PayrollSettings.objects.create()


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
