"""Bring in the 'Staff & Costs' sheet of PB_Master_File.xlsx: staff with monthly salaries, and the monthly
overheads. Only runs on the real Pondo database (the one with recipes) and never adds anything twice."""
from decimal import Decimal as D

from django.db import migrations

STAFF = [  # (job, name, monthly salary, department, note, gender)
    ("Manager", "Jurie", 4000, "admin", "", ""),
    ("Manager", "Dillan", None, "admin", "Salary not filled in on the Excel sheet.", ""),
    ("Cakes & Confec (Supervisor)", "Sydney", 550, "production", "Supervisor and main Confectioner", ""),
    ("Cakes & Confec", "Chris", 450, "production", "Confectioner", ""),
    ("Cakes & Confec", "Mike", 450, "production", "Confectioner", ""),
    ("Pies", "Herbert", 450, "production", "Pie Production", ""),
    ("Pies", "Natalie", 400, "production", "Pie Production", ""),
    ("Burgers", "Jambo", 430, "production", "Burgers", ""),
    ("Burgers & Pies Assistant", "Allan", 400, "production", "Burgers & Pie Cook", ""),
    ("Savoury", "Kofi", 450, "production", "All pie fillings and savoury lines", ""),
    ("Night Shift", "Wellington", 450, "production", "Breads & Rolls & morning goods", ""),
    ("Night Shift", "Talent", 450, "production", "Breads & Rolls & morning goods", ""),
    ("Night Shift", "Oscar", 450, "production", "Breads & Rolls & morning goods", ""),
    ("Night Shift", "Henry", 450, "production", "Breads & Rolls & morning goods", ""),
    ("Night Shift", "Clive", 450, "production", "Breads & Rolls & morning goods", ""),
    ("Packing / Sealing / Dispatch / Quality", "Nyasha", 380, "production", "Quality control & orders", ""),
    ("Counter hand", "Counter hand 1", 380, "shop", "Packing stock & serving customers", "M"),
    ("Counter hand", "Counter hand 2", 380, "shop", "Packing stock & serving customers", "M"),
    ("Counter hand / Cashier", "Cashier 1", 430, "shop", "Cashier & serving customers", "F"),
    ("Counter hand / Cashier", "Cashier 2", 430, "shop", "Cashier", "F"),
    ("Counter hand / Cashier", "Cashier 3", 430, "shop", "Cashier", "F"),
    ("Security Guard", "Security guard 1", 380, "security", "Security", "M"),
    ("Security Guard", "Security guard 2", 380, "security", "Security", "M"),
]
OVERHEADS = [("Rent", 3000), ("ZESA (electricity)", 3000), ("Gas", 1000), ("Water", 300), ("Fuel", 200),
             ("Internet", 50), ("POS", 10), ("Phone", 18), ("Cleaning material", 200), ("Repairs", 200),
             ("ZIMRA licence", 50), ("Insurance", 150)]


def add(apps, schema_editor):
    if not apps.get_model("costing", "Recipe").objects.exists():
        return  # an empty (test) database – nothing to bring in
    Overhead = apps.get_model("core", "Overhead")
    if not Overhead.objects.exists():
        for i, (name, cost) in enumerate(OVERHEADS):
            Overhead.objects.create(name=name, monthly_cost=D(cost), sort_order=i)
    Employee = apps.get_model("staff", "Employee")
    for job, name, pay, dept, note, gender in STAFF:
        if Employee.objects.filter(first_name__iexact=name).exists():
            continue
        placeholder = name[-1].isdigit()
        notes = note
        if placeholder:
            notes = (note + ". " if note else "") + "Name not on the Excel sheet yet – type the real name."
        elif pay is None:
            notes = note
        Employee.objects.create(first_name=name, last_name="", job_title=job, department=dept, gender=gender,
                                pay_type="monthly", rate=D(pay or 0), notes=notes)


class Migration(migrations.Migration):
    dependencies = [("staff", "0004_surname_optional"), ("core", "0003_overhead_companysettings_gp_override_and_more"),
                    ("costing", "0003_ingredient_reorder_level_ingredient_stock_par_and_more")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
