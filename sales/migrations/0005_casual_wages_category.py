from django.db import migrations


def add(apps, schema_editor):
    C = apps.get_model("sales", "ExpenseCategory")
    if not C.objects.filter(name__iexact="Casual wages & overtime").exists():
        C.objects.create(name="Casual wages & overtime", sort_order=1)


class Migration(migrations.Migration):
    dependencies = [("sales", "0004_expense_vat")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
