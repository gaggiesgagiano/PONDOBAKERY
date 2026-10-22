"""GP below 35% shows in solid red (was 45%). Only changes the setting if it was still the old 45%."""
from decimal import Decimal

from django.db import migrations, models


def to_35(apps, schema_editor):
    CompanySettings = apps.get_model("core", "CompanySettings")
    CompanySettings.objects.filter(gp_low=Decimal("0.45")).update(gp_low=Decimal("0.35"))


class Migration(migrations.Migration):
    dependencies = [("core", "0007_split_rights")]
    operations = [
        migrations.AlterField("companysettings", "gp_low", models.DecimalField("GP warning below", max_digits=6, decimal_places=4,
                              default=Decimal("0.35"), help_text="Products below this GP show red")),
        migrations.RunPython(to_35, migrations.RunPython.noop),
    ]
