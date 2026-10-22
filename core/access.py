"""Who may see or change what.

Each area has a level: 0 = no access, 1 = can look, 2 = can look and change.
"See costs & profit" separately controls ingredient prices, recipe costs and gross profit.
The Manager (the superuser login) can always do everything.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

NONE, VIEW, EDIT = 0, 1, 2
LEVELS = [(NONE, "No access"), (VIEW, "Can look"), (EDIT, "Can look & change")]

# area key, label, explanation, built yet?
AREAS = [
    ("sales", "Sales & cash-up", "Typing the day's sales, cash-ups, expenses, product sales", True),
    ("invoices", "Invoices & quotes", "Tax invoices, quotations, customers", True),
    ("deliveries", "Deliveries & drivers", "Sending orders with a driver, drivers and their ID cards", True),
    ("production", "Production plans", "Day / night shift plans and their ingredient lists", True),
    ("waste", "Waste", "The waste log", True),
    ("recipes", "Recipes", "Recipe list, method, ingredients and quantities, printing recipe cards", True),
    ("ingredients", "Ingredients", "Ingredient list, suppliers, pack sizes", True),
    ("prices", "Products & prices", "Selling prices, changing prices, printing price cards", True),
    ("stock", "Stock & orders", "Stock levels, suppliers, orders, goods received (GRV), stock takes", True),
    ("equipment", "Equipment", "Equipment register and the monthly equipment count", True),
    ("staff", "Staff & payroll", "Staff records, advances, leave, pay runs and payslips", True),
    ("money", "Money & accounts", "Cash book (safe, bank, EcoCash), paying suppliers, VAT, balance sheet – incl. the owner's money", True),
    ("letters", "Letters", "Typing, saving, printing and deleting letters on the Pondo letterhead", True),
    ("sops", "SOP file", "Reading the SOPs (look) – or writing, changing, approving and recording sign-offs (change)", True),
]

# how the tick list is grouped (the same groups as the menu)
AREA_GROUPS = [
    ("Freight & Logistics", ["deliveries"]),
    ("Procurement & Inventory", ["ingredients", "stock", "waste", "equipment"]),
    ("Finance", ["money"]),
    ("Production", ["production", "recipes", "prices"]),
    ("HR", ["staff", "sops"]),
    ("Administration", ["letters"]),
    ("Sales", ["sales", "invoices"]),
]

ALL = {"recipes": EDIT, "ingredients": EDIT, "prices": EDIT, "production": EDIT, "stock": EDIT, "sales": EDIT,
       "invoices": EDIT, "deliveries": EDIT, "waste": EDIT, "equipment": EDIT, "sops": VIEW}
# The Manager (the top login) can always do everything, plus Settings and Users.
# These are the starting rights for everybody else - each can be fine-tuned per person afterwards.
PRESETS = {
    "assistant_manager": {"label": "Assistant Manager", "help": "Everything, also staff & payroll (not Settings or Users)",
                          "levels": {**ALL, "staff": EDIT, "sops": EDIT}, "see_costs": True, "backup": True},
    "supervisor": {"label": "Supervisor", "help": "Everything except staff & payroll",
                   "levels": {**ALL, "staff": NONE}, "see_costs": True, "backup": True},
    "admin": {"label": "Admin", "help": "Everything except staff & payroll",
              "levels": {**ALL, "staff": NONE}, "see_costs": True, "backup": False},
    "cashier": {"label": "Cashier", "help": "Sales & cash-up, invoices, deliveries; can look at selling prices",
                "levels": {"recipes": NONE, "ingredients": NONE, "prices": VIEW, "production": NONE, "stock": NONE,
                           "sales": EDIT, "staff": NONE, "invoices": EDIT, "deliveries": EDIT, "waste": NONE, "equipment": NONE, "sops": VIEW}, "see_costs": False, "backup": False},
    "baker": {"label": "Baker", "help": "Only recipes - to look at them and print recipe cards (no costs)",
              "levels": {"recipes": VIEW, "ingredients": NONE, "prices": NONE, "production": NONE, "stock": NONE,
                         "sales": NONE, "staff": NONE, "invoices": NONE, "deliveries": NONE, "waste": NONE, "equipment": NONE, "sops": VIEW}, "see_costs": False, "backup": False},
    "none": {"label": "Nothing ticked", "help": "Start with no access and tick everything yourself",
             "levels": {}, "see_costs": False, "backup": False},
}
# rights saved under an old name keep their label
OLD_LABELS = {"manager": "Manager"}
DEFAULT_ROLE = "supervisor"


class Rights:
    """What one user may do. Use in templates as {{ can.recipes_edit }}, {{ can.costs }} etc."""

    def __init__(self, user):
        self.user = user
        self.owner = bool(user and user.is_authenticated and user.is_superuser)
        acc = None
        if user and user.is_authenticated and not self.owner:
            from .models import Access

            acc = Access.objects.filter(user=user).first()
            if acc is None:
                acc = Access.from_preset(user, DEFAULT_ROLE)
        self.acc = acc

    def level(self, area):
        if self.owner:
            return EDIT
        if self.acc is None:
            return NONE
        return getattr(self.acc, area, NONE)

    def has(self, area, need=VIEW):
        return self.level(area) >= need

    @property
    def costs(self):
        return self.owner or bool(self.acc and self.acc.see_costs)

    @property
    def backup(self):
        return self.owner or bool(self.acc and self.acc.backup)

    def __getattr__(self, name):
        # can.recipes_view / can.recipes_edit
        for suffix, need in (("_view", VIEW), ("_edit", EDIT)):
            if name.endswith(suffix):
                area = name[: -len(suffix)]
                if area in dict((a[0], a) for a in AREAS):
                    return self.has(area, need)
        raise AttributeError(name)


def rights(request):
    if not hasattr(request, "_rights"):
        request._rights = Rights(request.user)
    return request._rights


def need(area=None, level=VIEW, costs=False, backup=False, owner=False):
    """View decorator: refuse politely when the user lacks the right."""

    def deco(view):
        @wraps(view)
        def wrapped(request, *a, **kw):
            r = rights(request)
            ok = True
            if owner and not r.owner:
                ok = False
            if area and not r.has(area, level):
                ok = False
            if costs and not r.costs:
                ok = False
            if backup and not r.backup:
                ok = False
            if not ok:
                messages.error(request, "You don't have rights for that page. Ask the Manager if you need it.")
                return redirect("core:dashboard")
            return view(request, *a, **kw)

        return wrapped

    return deco
