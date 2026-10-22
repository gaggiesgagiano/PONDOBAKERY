from django.db import migrations


def tills(apps, schema_editor):
    Till = apps.get_model("till", "Till")
    for i, (name, code) in enumerate((("Till 1", "T1"), ("Till 2", "T2"))):
        Till.objects.get_or_create(name=name, defaults={"code": code, "sort_order": i})


class Migration(migrations.Migration):
    dependencies = [("till", "0001_initial")]
    operations = [migrations.RunPython(tills, migrations.RunPython.noop)]
