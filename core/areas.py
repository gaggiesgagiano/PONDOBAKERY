"""The program's areas: menu groups, brand colour, illustration and manual chapter for every page.

Brand colour pairings (guidelines p.19): orange and teal backgrounds take Bakery Cream; burgundy takes Cream or Warm Orange;
warm orange takes Burgundy (or Cream); Bakery Cream takes Burgundy, Teal, Orange or Warm Orange.
"""
from django.urls import NoReverseMatch, reverse

ICONS = {
 "gpcheck": "<path d=\"M4 20h16\"/><path d=\"M6 16l4-5 3 3 5-7\"/><circle cx=\"18\" cy=\"7\" r=\"1.6\"/>",
 "dashboard": "<rect x=\"3\" y=\"3\" width=\"7\" height=\"9\" rx=\"1.5\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"5\" rx=\"1.5\"/><rect x=\"14\" y=\"12\" width=\"7\" height=\"9\" rx=\"1.5\"/><rect x=\"3\" y=\"16\" width=\"7\" height=\"5\" rx=\"1.5\"/>",
 "recipes": "<path d=\"M4 19V6a2 2 0 0 1 2-2h12v15H6a2 2 0 0 0-2 2z\"/><path d=\"M8 8h6M8 12h5\"/>",
 "ingredients": "<path d=\"M5 8h14l-1.5 12h-11z\"/><path d=\"M9 8V6a3 3 0 0 1 6 0v2\"/>",
 "prices": "<path d=\"M20 12l-8 8-9-9V3h8z\"/><circle cx=\"7.5\" cy=\"7.5\" r=\"1.5\"/>",
 "production": "<rect x=\"3\" y=\"5\" width=\"18\" height=\"16\" rx=\"2\"/><path d=\"M3 10h18M8 3v4M16 3v4\"/>",
 "waste": "<path d=\"M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3\"/>",
 "stock": "<path d=\"M21 8l-9-5-9 5 9 5z\"/><path d=\"M3 8v8l9 5 9-5V8\"/>",
 "orders": "<path d=\"M3 4h2.5l2.2 11h10.6l2-8H6.3\"/><circle cx=\"9\" cy=\"19.5\" r=\"1.5\"/><circle cx=\"17\" cy=\"19.5\" r=\"1.5\"/>",
 "grv": "<path d=\"M9 4h6v3H9z\"/><path d=\"M15 5h3a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h3\"/><path d=\"M8.5 14l2.5 2.5 4.5-5\"/>",
 "equipment": "<rect x=\"3\" y=\"7\" width=\"18\" height=\"13\" rx=\"2\"/><path d=\"M7 7V4h10v3M3 12h18M10 12v3h4v-3\"/>",
 "fiscal": "<path d=\"M6 2h12v20l-3-2-3 2-3-2-3 2z\"/><path d=\"M9 7h6M9 11h6\"/><rect x=\"9.5\" y=\"14\" width=\"5\" height=\"4\"/>",
 "till": "<rect x=\"3\" y=\"11\" width=\"18\" height=\"10\" rx=\"2\"/><path d=\"M6 11V4h12v7\"/><path d=\"M9 7h6M7 15h2M11 15h2M15 15h2M7 18h10\"/>",
 "sales": "<rect x=\"2\" y=\"6\" width=\"20\" height=\"13\" rx=\"2\"/><circle cx=\"12\" cy=\"12.5\" r=\"2.5\"/>",
 "deliveries": "<path d=\"M2 6h12v10H2z\"/><path d=\"M14 9h4.5l3.5 3.5V16h-8z\"/><circle cx=\"6.5\" cy=\"17.5\" r=\"2\"/><circle cx=\"17.5\" cy=\"17.5\" r=\"2\"/>",
 "invoices": "<path d=\"M6 2h9l5 5v15H6z\"/><path d=\"M14 2v6h6M9 13h8M9 17h6\"/>",
 "staff": "<circle cx=\"9\" cy=\"8\" r=\"3.5\"/><path d=\"M2.5 20a6.5 6.5 0 0 1 13 0\"/><path d=\"M17 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6\"/>",
 "money": "<rect x=\"2.5\" y=\"6\" width=\"19\" height=\"14\" rx=\"2.5\"/><path d=\"M2.5 10h19\"/><path d=\"M5 6l11-3 1.5 3\"/><circle cx=\"16.5\" cy=\"15\" r=\"1.3\"/>",
 "reports": "<path d=\"M4 20V10M10 20V4M16 20v-7M22 20H2\"/>",
 "help": "<circle cx=\"12\" cy=\"12\" r=\"9.5\"/><path d=\"M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01\"/>",
 "brand": "<path d=\"M12 2.5l2.1 3.2 3.7-1-.4 3.8 3.5 1.6-2.6 2.9 2.6 2.9-3.5 1.6.4 3.8-3.7-1L12 21.5l-2.1-3.2-3.7 1 .4-3.8-3.5-1.6L5.7 12 3.1 9.1l3.5-1.6-.4-3.8 3.7 1z\"/>",
 "settings": "<circle cx=\"12\" cy=\"12\" r=\"3\"/><path d=\"M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z\"/>",
 "backup": "<path d=\"M8 3h8v6H8z\"/><rect x=\"5\" y=\"9\" width=\"14\" height=\"12\" rx=\"2\"/><path d=\"M10 5v2M14 5v2\"/>",
 "excel": "<rect x=\"3\" y=\"3\" width=\"18\" height=\"18\" rx=\"2\"/><path d=\"M3 9h18M9 9v12M15 9v12M3 15h18\"/>",
 "sops": "<path d=\"M9 3h6v3H9z\"/><path d=\"M15 4.5h3a1 1 0 0 1 1 1V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1h3\"/><path d=\"M8.5 11h7M8.5 14.5h7M8.5 18h4\"/>",
 "exams": "<rect x=\"5\" y=\"10\" width=\"14\" height=\"11\" rx=\"2\"/><path d=\"M8 10V7a4 4 0 0 1 8 0v3\"/><path d=\"M12 14.5v3\"/>",
 "letters": "<path d=\"M3 6h18v12H3z\"/><path d=\"M3 7l9 6 9-6\"/>",
 "forms": "<path d=\"M7 3h7l4 4v14H7z\"/><path d=\"M13 3v5h5\"/><path d=\"M10 12h5M10 15.5h5M10 19h3\"/><path d=\"M4 6v15h10\"/>",
 "manual": "<path d=\"M3 5.5C5.5 4 8.5 4 12 6c3.5-2 6.5-2 9-.5V20c-2.5-1.5-5.5-1.5-9 .5-3.5-2-6.5-2-9-.5z\"/><path d=\"M12 6v14.5\"/>"
}

# key: (label, url name, colour, illustration, manual chapter, right needed)
ITEMS = {
    "dashboard": ("Dashboard", "core:dashboard", "orange", "donut", "dashboard", None),
    "till": ("Till", "till:start", "teal", "cookie", "sales", "sales_edit"),
    "fiscal": ("Fiscal (ZIMRA)", "fiscal:home", "teal", "cookie", "sales", "sales_edit"),
    "sales": ("Sales & Cash-Up", "sales:daily", "teal", "cookie", "sales", "sales_view"),
    "production": ("Production", "production:plans", "warm", "bread", "production", "production_view"),
    "waste": ("Waste", "production:waste_list", "burgundy", "pie", "waste", "waste_view"),
    "recipes": ("Recipes & Prices", "costing:recipes", "burgundy", "cupcake", "recipes", "recipes_view"),
    "ingredients": ("Ingredients", "costing:ingredients", "teal", "bun", "ingredients", "ingredients_view"),
    "gpcheck": ("GP check", "costing:recipes", "orange", "glazed_bun", "prices", "costs"),
    "prices": ("Products & Prices", "costing:prices", "orange", "glazed_bun", "prices", "prices_view"),
    "stock": ("Stock", "stock:home", "warm", "samoosa", "stock", "stock_view"),
    "orders": ("Orders", "stock:orders", "orange", "cookie", "orders", "stock_view"),
    "grv": ("GRV – goods received", "stock:grvs", "teal", "bread", "grv", "stock_view"),
    "equipment": ("Equipment", "equipment:register", "teal", "pie", "equipment", "equipment_view"),
    "invoices": ("Invoices & Quotes", "invoices:list", "orange", "cookie", "invoices", "invoices_view"),
    "deliveries": ("Deliveries", "invoices:deliveries", "burgundy", "samoosa", "deliveries", "deliveries_view"),
    "staff": ("Staff & Payroll", "staff:people", "burgundy", "donut", "staff", "staff_view"),
    "money": ("Money & accounts", "money:home", "teal", "cookie", "money", "money_view"),
    "reports": ("Reports", "reports:month_end", "teal", "cupcake", "reports", "costs"),
    "excel": ("Excel downloads", "core:excel", "warm", "bread", "start", None),
    "manual": ("Staff manual", "core:manual", "orange", "bread", "start", None),
    "sops": ("SOP file", "core:sops", "teal", "bun", "sops", "sops_view"),
    "exams": ("SOP exams", "core:exams", "burgundy", "pie", "sops", "owner"),
    "forms": ("Forms", "core:forms", "teal", "cookie", "letters", None),
    "letters": ("Letters", "core:letters", "burgundy", "cupcake", "letters", "letters_view"),
    "help": ("Quick help", "core:help", "teal", "bun", "start", None),
    "brand": ("Our Brand", "core:brand", "burgundy", "starburst", "brand", None),
    "settings": ("Settings", "core:settings", "warm", "samoosa", "owner", "owner"),
    "backup": ("Back up now", "core:backup", "teal", "glazed_bun", "owner", "backup"),
}
GROUPS = [
    ("", ["dashboard"]),   # always at the top, no heading
    ("Freight & Logistics", ["deliveries"]),
    ("Procurement", ["orders", "grv", "ingredients"]),
    ("Inventory", ["stock", "waste", "equipment"]),
    ("Finance", ["money", "reports", "gpcheck", "excel"]),
    ("Production", ["production", "recipes", "prices"]),
    ("Tax & Compliance", ["fiscal"]),
    ("HR", ["staff", "sops", "exams"]),
    ("Administration", ["letters", "forms", "settings", "backup", "manual", "help", "brand"]),
    ("Sales", ["till", "sales", "invoices"]),
]
COLOURS = {  # background, text, softer text
    "orange": ("#e56026", "#fff3d7", "#ffe3c4"),
    "teal": ("#218d80", "#fff3d7", "#d6f0eb"),
    "burgundy": ("#7a1315", "#fff3d7", "#ffd2b0"),
    "warm": ("#f89b47", "#7a1315", "#5c0e10"),
}


def area_of(match):
    """Which area a page belongs to (for its colour band and its manual chapter)."""
    if match is None:
        return "dashboard"
    ns, name = match.namespace, match.url_name or ""
    if ns == "costing":
        if "ingredient" in name:
            return "ingredients"
        if name in ("prices", "cards", "cards_print"):
            return "prices"
        if name == "lists":
            return "settings"
        return "recipes"
    if ns == "production":
        return "waste" if "waste" in name else "production"
    if ns == "invoices" and ("deliver" in name or "driver" in name):
        return "deliveries"
    if ns == "stock" and name.startswith("grv"):
        return "grv"
    if ns == "stock" and name.startswith("order"):
        return "orders"
    if ns == "till":
        return "till"
    if ns == "fiscal":
        return "fiscal"
    if ns == "money":
        return "money"
    if ns in ("sales", "stock", "equipment", "invoices", "staff", "reports"):
        return ns
    if ns == "core":
        if name in ("settings", "users", "user_rights", "cards", "cards_print", "card_new", "card_stop", "card_all", "card_link", "changelog", "targets", "look_business", "password", "email_settings"):
            return "settings"
        if name in ("manual", "help", "brand", "backup"):
            return name
        if name in ("forms", "form_print"):
            return "forms"
        if name.startswith("exam"):
            return "exams"
        if name.startswith("sop"):
            return "sops"
        if name.startswith("letter"):
            return "letters"
        if name in ("excel", "excel_file"):
            return "excel"
        if name == "look":
            return "brand"
    return "dashboard"


def menu(can, current):
    groups = []
    for title, keys in GROUPS:
        items = []
        for k in keys:
            label, url, colour, art, chapter, right = ITEMS[k]
            if right == "owner":
                if not can.owner:
                    continue
            elif k == "prices" and getattr(can, "recipes_view", False):
                continue  # prices are on the Recipes & Prices page
            elif right and not getattr(can, right, False):
                continue
            try:
                href = reverse(url)
            except NoReverseMatch:
                continue
            if k == "gpcheck":
                href += "?gp_max=49.99"  # opens the products below 50% GP, ready to adjust the prices
            items.append({"key": k, "label": label, "href": href, "colour": colour, "icon": ICONS.get(k, ""), "on": k == current})
        if items:
            groups.append({"title": title, "items": items})
    return groups


def area_info(key):
    label, url, colour, art, chapter, right = ITEMS[key]
    bg, ink, ink2 = COLOURS[colour]
    return {"key": key, "label": label, "colour": colour, "art": art, "chapter": chapter,
            "ink_name": "burgundy" if colour == "warm" else "cream", "bg": bg, "ink": ink}
