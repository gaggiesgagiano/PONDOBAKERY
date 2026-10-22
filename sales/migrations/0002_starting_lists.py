from django.db import migrations

METHODS = [("Cash (US$)", True), ("Swipe / card", False), ("EcoCash", False), ("Bank transfer", False)]
CATEGORIES = ["Gas & fuel", "Electricity", "Water", "Rent", "Transport & delivery", "Repairs & maintenance",
              "Cleaning & hygiene", "Small buys (cash)", "Staff meals", "Bank charges", "Phone & internet",
              "Stationery & admin", "Licences & fees", "Other"]


def add(apps, schema_editor):
    PaymentMethod = apps.get_model("sales", "PaymentMethod")
    ExpenseCategory = apps.get_model("sales", "ExpenseCategory")
    for i, (name, cash) in enumerate(METHODS):
        PaymentMethod.objects.get_or_create(name=name, defaults={"is_cash": cash, "sort_order": i})
    for i, name in enumerate(CATEGORIES):
        ExpenseCategory.objects.get_or_create(name=name, defaults={"sort_order": i})


class Migration(migrations.Migration):
    dependencies = [("sales", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
