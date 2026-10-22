"""The staff manual: one chapter per area of the program, printable for each role."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .access import rights

# key, title, colour, illustration, who uses it
CHAPTERS = [  # in the same order as the menu on the left
    ("start", "Getting started", "orange", "donut", "Everybody"),
    ("guide", "The owner's guide – how it all fits together", "burgundy", "donut", "Manager"),
    ("dashboard", "The dashboard & Short Cuts", "orange", "donut", "Everybody"),
    ("sales", "Sales, cash-up & over / short", "teal", "cookie", "Cashier · Supervisors · Managers"),
    ("invoices", "Invoices & quotes", "orange", "cookie", "Cashier · Supervisors · Managers"),
    ("deliveries", "Deliveries with a driver", "burgundy", "samoosa", "Cashier · Supervisors · Managers"),
    ("production", "Production plans", "warm", "bread", "Supervisors · Managers"),
    ("waste", "Waste", "burgundy", "pie", "Supervisors · Managers"),
    ("recipes", "Recipes & Prices", "burgundy", "cupcake", "Baker · Supervisors · Managers"),
    ("prices", "Prices, GP check & price cards", "orange", "glazed_bun", "Cashier · Supervisors · Managers"),
    ("ingredients", "Ingredients", "teal", "bun", "Supervisors · Managers"),
    ("stock", "Stock, stock take & suppliers", "warm", "samoosa", "Supervisors · Managers"),
    ("orders", "Orders – e-mail & WhatsApp", "orange", "cookie", "Supervisors · Managers"),
    ("grv", "GRV – goods received", "teal", "bread", "Supervisors · Managers"),
    ("equipment", "Equipment", "teal", "pie", "Supervisors · Managers"),
    ("staff", "Staff & payroll", "burgundy", "donut", "Operations & Assistant Manager"),
    ("money", "Money & accounts – the books", "teal", "cookie", "Manager · people with the Money right"),
    ("reports", "Reports & month end", "teal", "cupcake", "Supervisors · Managers"),
    ("sops", "The SOP file", "teal", "bun", "Everybody"),
    ("letters", "Letters, letterhead & forms", "burgundy", "cupcake", "People with the Letters right"),
    ("owner", "Settings, users, other computers & backups", "warm", "samoosa", "Manager"),
    ("brand", "Our brand", "burgundy", "starburst", "Everybody"),
    ("glossary", "Words we use", "teal", "bun", "Everybody"),
]
ROLES = {
    "cashier": ("Cashier", ["start", "dashboard", "sales", "prices", "invoices", "deliveries", "brand", "glossary"]),
    "baker": ("Baker", ["start", "dashboard", "recipes", "brand", "glossary"]),
    "supervisor": ("Supervisor / Admin", [c[0] for c in CHAPTERS if c[0] not in ("staff", "money", "owner", "guide", "letters")]),
    "assistant_manager": ("Assistant Manager", [c[0] for c in CHAPTERS if c[0] not in ("money", "owner", "guide", "letters")]),
    "owner": ("Manager", [c[0] for c in CHAPTERS]),
    "all": ("Everybody – the whole manual", [c[0] for c in CHAPTERS]),
}
NEEDS = {"sales": "sales_view", "invoices": "invoices_view", "deliveries": "deliveries_view", "production": "production_view", "waste": "waste_view",
         "recipes": "recipes_view", "ingredients": "ingredients_view", "prices": "prices_view", "stock": "stock_view", "orders": "stock_view", "grv": "stock_view", "letters": "letters_view", "sops": "sops_view",
         "equipment": "equipment_view", "staff": "staff_view", "money": "money_view", "reports": "costs", "owner": "owner", "guide": "owner"}


def _mine(can):
    keys = []
    for key, *_ in CHAPTERS:
        need = NEEDS.get(key)
        if need is None or getattr(can, need, False):
            keys.append(key)
    return keys


def _pick(request):
    can = rights(request)
    role = request.GET.get("role", "mine")
    if role in ROLES:
        keys, label = ROLES[role][1], ROLES[role][0]
    else:
        role, keys, label = "mine", _mine(can), "My chapters"
    one = request.GET.get("ch")
    if one in dict((c[0], c) for c in CHAPTERS):
        keys = [one]
    chapters = [{"key": k, "title": t, "colour": c, "art": a, "ink": "burgundy" if c == "warm" else "cream", "who": w}
                for k, t, c, a, w in CHAPTERS if k in keys]
    for n, ch in enumerate(chapters, 1):
        ch["n"] = n
    return {"chapters": chapters, "show": set(keys), "role": role, "role_label": label, "roles": ROLES,
            "one": one, "today": timezone.localdate()}


@login_required
def manual(request):
    return render(request, "core/manual.html", {**_pick(request), "screen": True})


@login_required
def manual_print(request):
    ctx = _pick(request)
    ctx["low_ink"] = request.GET.get("ink") == "low"
    return render(request, "core/manual_print.html", ctx)
