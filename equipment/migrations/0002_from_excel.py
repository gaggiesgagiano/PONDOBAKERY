"""Categories and places from the Excel 'Equipment Lists' sheet, and – on the real Pondo database only –
the 143 items of the 'Equipment Register' (costs in US$ excl. VAT, as worked out in the Excel file)."""
import json
from decimal import Decimal as D
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "excel_equipment.json"


def add(apps, schema_editor):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    Cat = apps.get_model("equipment", "EquipmentCategory")
    Loc = apps.get_model("equipment", "Location")
    for n, (name, life) in enumerate(data["categories"]):
        Cat.objects.get_or_create(name=name, defaults={"life_years": D(life), "sort_order": n})
    for n, name in enumerate(data["locations"]):
        Loc.objects.get_or_create(name=name, defaults={"sort_order": n})
    if not apps.get_model("costing", "Recipe").objects.exists():
        return  # empty (test) database
    Item = apps.get_model("equipment", "Item")
    if Item.objects.exists():
        return
    for it in data["items"]:
        cat, _ = Cat.objects.get_or_create(name=it["category"], defaults={"life_years": D(5)})
        loc = Loc.objects.get_or_create(name=it["location"])[0] if it["location"] else None
        Item.objects.create(asset_no=it["asset_no"], description=it["description"][:200], category=cat, location=loc,
                            serial=it["serial"][:80], supplier=it["supplier"][:120], purchase_date=it["purchase_date"],
                            unit_cost=D(it["unit_cost"]), qty=it["qty"], scrap_value=D(it["scrap"]),
                            life_override=D(str(it["life_override"])) if it["life_override"] else None, notes=it["notes"])


class Migration(migrations.Migration):
    dependencies = [("equipment", "0001_initial"), ("costing", "0003_ingredient_reorder_level_ingredient_stock_par_and_more")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
