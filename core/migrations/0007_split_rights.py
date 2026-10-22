"""Invoices, deliveries, waste and equipment get their own tick in the rights.
Everybody keeps what they had: invoices & deliveries copy Sales, waste copies Production, equipment copies Stock."""
from django.db import migrations, models


def copy_rights(apps, schema_editor):
    Access = apps.get_model("core", "Access")
    for a in Access.objects.all():
        a.invoices = a.deliveries = a.sales
        a.waste = a.production
        a.equipment = a.stock
        a.save()


class Migration(migrations.Migration):
    dependencies = [("core", "0006_my_jobs")]
    operations = [
        migrations.AddField("access", "invoices", models.PositiveSmallIntegerField(choices=[(0, "No access"), (1, "Can look"), (2, "Can look & change")], default=0)),
        migrations.AddField("access", "deliveries", models.PositiveSmallIntegerField(choices=[(0, "No access"), (1, "Can look"), (2, "Can look & change")], default=0)),
        migrations.AddField("access", "waste", models.PositiveSmallIntegerField(choices=[(0, "No access"), (1, "Can look"), (2, "Can look & change")], default=0)),
        migrations.AddField("access", "equipment", models.PositiveSmallIntegerField(choices=[(0, "No access"), (1, "Can look"), (2, "Can look & change")], default=0)),
        migrations.RunPython(copy_rights, migrations.RunPython.noop),
    ]
