"""Short Cuts (once called Today's jobs) on the dashboard: one tile per job, coloured like its area, showing done / to do.

Everybody chooses their own jobs (Choose jobs): the program's jobs below, plus jobs they add themselves
("Clean the display fridges"), which they tick off each day.
"""
import datetime

from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .areas import ICONS, ITEMS

CHECK = '<path d="M4 12.5l5 5L20 6.5"/>'


def _job(area, title, sub, url, done=None, label=None):
    colour, art = ITEMS[area][2], ITEMS[area][3]
    return {"area": area, "colour": colour, "art": art, "ink": "burgundy" if colour == "warm" else "cream",
            "icon": ICONS.get(area, ""), "title": title, "sub": sub, "url": url, "done": done,
            "label": label or ("✓ Done" if done else "To do" if done is False else "")}


# ----------------------------------------------------------------- the program's jobs
def j_sales(can, d):
    from sales.models import DailySales

    typed = DailySales.objects.filter(date=d).exists()
    return _job("sales", "Type the day's sales", "sales are typed" if typed else "from the till's end-of-day report",
                reverse("sales:daily_edit", args=[d.isoformat()]), typed)


def j_cashup(can, d):
    from sales.models import CashUp

    cus = list(CashUp.objects.filter(date=d))
    waiting = CashUp.objects.filter(signed_off_at__isnull=True).count()
    sub = f"{len(cus)} till{'s' if len(cus) != 1 else ''} cashed up" if cus else "count the drawer after closing"
    if waiting and can.sales_edit:
        sub += f" · {waiting} to sign off"
    return _job("sales", "Cash-up", sub, reverse("sales:cashups"), bool(cus))


def j_plan(can, d):
    from production.models import ProductionPlan

    plans = list(ProductionPlan.objects.filter(date=d))
    return _job("production", "Production plan", ", ".join(p.get_shift_display() for p in plans) if plans
                else "day & night shift", reverse("production:plans"), bool(plans))


def j_waste(can, d):
    from production.models import WasteLog

    yday = d - datetime.timedelta(days=1)
    logged = WasteLog.objects.filter(date=yday).exists()
    return _job("waste", "Waste log", f"for {yday:%a %d %b}", reverse("production:waste_list"), logged)


def j_deliveries(can, d):
    from invoices.deliveries import out_summary

    out = out_summary()
    if out["n"]:
        return _job("deliveries", "Deliveries", f"{out['n']} out with drivers"
                    + (f" · ${out['back']:,.2f} to come back" if out["back"] else ""),
                    reverse("invoices:deliveries"), False, "Check")
    if can.deliveries_edit:
        return _job("deliveries", "Deliveries", "send an order with a driver", reverse("invoices:delivery_new"))
    return None


def j_receiving(can, d):
    return _job("grv", "Receiving", "goods in from suppliers (GRV)", reverse("stock:grvs"))


def j_low_stock(can, d):
    from stock.levels import stock_rows

    rows, _ = stock_rows(low_only=True)
    return _job("stock", "Low stock", f"{len(rows)} item{'s' if len(rows) != 1 else ''} below the re-order level"
                if rows else "nothing below the re-order level", reverse("stock:home") + "?low=1", not rows,
                "Order" if rows else None)


def j_orders(can, d):
    from stock.models import PurchaseOrder

    n = PurchaseOrder.objects.filter(status=PurchaseOrder.SENT).count()
    return _job("orders", "Orders on the way", f"{n} order{'s' if n != 1 else ''} not received yet" if n
                else "no orders waiting", reverse("stock:orders"))


def j_stocktake(can, d):
    from stock.levels import last_count

    lc = last_count()
    days = (d - lc.date).days if lc else None
    due = days is None or days >= 7
    sub = "no stock take yet" if lc is None else f"last one {lc.date:%a %d %b} ({days} day{'s' if days != 1 else ''} ago)"
    return _job("stock", "Stock take", sub, reverse("stock:counts"), not due, "Due" if due else None)


def j_equipment(can, d):
    from equipment.models import EquipmentCount

    done = EquipmentCount.objects.filter(month=d.replace(day=1)).exists()
    return _job("equipment", "Equipment count", f"for {d:%B}", reverse("equipment:count"), done)


def j_prices(can, d):
    return _job("prices", "Price cards", "shelf cards & posters", reverse("costing:cards"))


def j_price_change(can, d):
    from costing.models import Recipe

    from .models import ChangeLog

    n = Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__isnull=True).count()
    if n:
        sub = f"{n} product{'s' if n != 1 else ''} without a price"
    else:
        last = ChangeLog.objects.filter(area="Prices").values_list("when", flat=True).first()
        sub = f"last change {timezone.localtime(last):%d %b}" if last else "type new selling prices"
    return _job("prices", "Change prices", sub, reverse("costing:prices") + "?edit=1")


def j_invoices(can, d):
    from invoices.models import Document

    open_ = Document.objects.filter(kind=Document.INVOICE, status=Document.OPEN)
    n, late = open_.count(), open_.filter(due__lt=d).count()
    return _job("invoices", "Unpaid invoices", (f"{n} not paid" + (f" · {late} overdue" if late else "")) if n
                else "all invoices are paid", reverse("invoices:list") + "?kind=invoice&status=open", not late,
                "Overdue" if late else None)


def j_quotes(can, d):
    from invoices.models import Document

    n = Document.objects.filter(kind=Document.QUOTE, status=Document.OPEN).count()
    return _job("invoices", "Open quotations", f"{n} waiting for the customer" if n else "none waiting",
                reverse("invoices:list") + "?kind=quote&status=open")


def j_payroll(can, d):
    from staff.models import PayRun

    run = PayRun.objects.filter(period=d.replace(day=1)).first()
    if run is None:
        return _job("staff", "Payroll", f"for {d:%B} – not started", reverse("staff:payruns"), False)
    return _job("staff", "Payroll", f"{d:%B}: {run.get_status_display().split(' –')[0].lower()}",
                reverse("staff:payrun", args=[run.pk]), run.status == PayRun.FINAL)


def j_add_staff(can, d):
    return _job("staff", "Add staff", "a new person – details, papers & photo", reverse("staff:person_new"))


def j_staff_papers(can, d):
    from staff.models import expiring_papers

    exp = expiring_papers(d)
    if not exp:
        return None
    gone = sum(1 for p in exp if p.expires < d)
    sub = " · ".join(x for x in (f"{gone} ran out" if gone else "",
                                 f"{len(exp) - gone} run out soon" if len(exp) > gone else "") if x)
    return _job("staff", "Staff papers", sub, reverse("staff:files"), False, "Check")


def j_month_end(can, d):
    nxt = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    left = (nxt - d).days - 1
    return _job("reports", "Month-end report", "last day of the month" if left == 0 else
                f"{left} day{'s' if left != 1 else ''} to month end", reverse("reports:month_end"))


def j_accountant(can, d):
    """Accountant report: in the first 10 days of a month it is last month's report, to send; later this month so far."""
    from reports.models import MonthClose

    first = d.replace(day=1)
    if d.day <= 10:
        last = (first - datetime.timedelta(days=1)).replace(day=1)
        mc = MonthClose.objects.filter(month=last).first()
        sent = bool(mc and mc.sent_to_accountant.strip())
        return _job("reports", "Accountant report", f"{last:%B} – " + ("sent" if sent else "print or download and send"),
                    reverse("reports:accountant") + f"?month={last:%Y-%m}", sent, None if sent else "Due")
    return _job("reports", "Accountant report", f"{first:%B} so far · 1st to {d:%d %b}",
                reverse("reports:accountant") + f"?month={first:%Y-%m}")


def j_backup(can, d, backup_due=False):
    if not backup_due:
        return None
    return _job("backup", "Back up", "today's cash-ups are not on the flash drive yet", reverse("core:backup"), False, "Due")


# ----------------------------------------------------------------- more short cuts (live where it is cheap to know)
def _link(area, title, sub, url_name, *args, query=""):
    try:
        return _job(area, title, sub, reverse(url_name, args=args) + query)
    except NoReverseMatch:
        return None


def j_till(can, d):
    from till.models import Shift, Till

    open_ = list(Shift.objects.filter(closed_at__isnull=True).select_related("till", "cashier"))
    tills = Till.objects.filter(active=True).count()
    if open_:
        sub = " · ".join(f"{s.label}: {s.cashier_name()}" for s in open_[:3]) + (f" · {tills - len(open_)} free" if tills > len(open_) else "")
        return _job("till", "Till", sub, reverse("till:start"), None, f"{len(open_)} open")
    return _job("till", "Till", "no till open – open one with a float", reverse("till:start"))


def j_fiscal(can, d):
    from fiscal import service

    if not service.active():
        return _job("fiscal", "Fiscal (ZIMRA)", "off – the till prints practice slips", reverse("fiscal:home"))
    c = service.counts()
    bits = [f"{c['pending']} waiting to send" if c["pending"] else "", f"{c['failed']} refused" if c["failed"] else ""]
    sub = " · ".join(b for b in bits if b) or "all slips are with ZIMRA"
    return _job("fiscal", "Fiscal (ZIMRA)", sub, reverse("fiscal:home"), not c["failed"], "Check" if c["failed"] else None)


def j_zwg_rate(can, d):
    from .models import CompanySettings

    cs = CompanySettings.get()
    if not cs.zwg_rate:
        return _job("settings", "ZWG rate", "not set – the till takes USD only", reverse("core:settings"), False, "Set it")
    when = f" · set {timezone.localtime(cs.zwg_rate_at):%d %b %H:%M}" if cs.zwg_rate_at else ""
    return _job("settings", "ZWG rate", f"ZWG {cs.zwg_rate:.2f} = US$1{when}", reverse("core:settings"))


def j_new_invoice(can, d):
    return _link("invoices", "New invoice", "a tax invoice for a customer", "invoices:new", query="?kind=invoice")


def j_new_quote(can, d):
    return _link("invoices", "New quotation", "a price quote for a customer", "invoices:new", query="?kind=quote")


def j_customers(can, d):
    from invoices.models import Customer

    n = Customer.objects.filter(active=True).count()
    return _link("invoices", "Customers", f"{n} customer{'s' if n != 1 else ''} – names, TIN & VAT numbers", "invoices:customers")


def j_sales_report(can, d):
    return _link("sales", "Sales report", "sales per day, week and month", "sales:report")


def j_expenses(can, d):
    from sales.models import Expense

    today = Expense.objects.filter(date=d)
    n = today.count()
    total = sum((e.amount for e in today), 0)
    return _link("sales", "Expenses", f"{n} today · ${total:,.2f}" if n else "nothing paid out today", "sales:expenses")


def j_new_order(can, d):
    return _link("orders", "New supplier order", "order stock from a supplier", "stock:order_new")


def j_suppliers(can, d):
    return _link("orders", "Suppliers", "names, contacts and account numbers", "stock:suppliers")


def j_ingredients(can, d):
    return _link("ingredients", "Ingredients", "pack sizes and buying prices", "costing:ingredients")


def j_waste_now(can, d):
    return _link("waste", "Write off waste", "type what was thrown away now", "production:waste_new")


def j_recipes(can, d):
    from costing.models import Recipe

    n = Recipe.objects.filter(active=True).count()
    return _link("recipes", "Recipes", f"{n} recipes – method, ingredients, cards", "costing:recipes")


def j_gp_check(can, d):
    return _link("gpcheck", "GP check", "products below 50% gross profit", "costing:recipes", query="?gp_max=49.99")


def j_money(can, d):
    return _link("money", "Cash book", "safe, bank and EcoCash", "money:home")


def j_pay_suppliers(can, d):
    return _link("money", "Pay suppliers", "what we owe and paying it", "money:creditors")


def j_vat(can, d):
    return _link("money", "VAT", f"VAT for {d:%B}", "money:vat")


def j_stock_results(can, d):
    return _link("reports", "Stock results", "real GP from the stock takes", "reports:stock")


def j_excel(can, d):
    return _link("excel", "Excel downloads", "lists and reports for Excel", "core:excel")


def j_staff_list(can, d):
    from staff.models import Employee

    try:
        n = Employee.objects.filter(active=True).count()
        sub = f"{n} people – details, leave, advances"
    except Exception:  # noqa: BLE001
        sub = "details, leave, advances"
    return _link("staff", "Staff list", sub, "staff:people")


def j_sops(can, d):
    return _link("sops", "SOP file", "how we do things – read and sign off", "core:sops")


def j_exams(can, d):
    return _link("exams", "SOP exams", "test what staff know", "core:exams")


def j_letters(can, d):
    return _link("letters", "New letter", "on the Pondo letterhead", "core:letter_new")


def j_forms(can, d):
    return _link("forms", "Blank forms", "food safety, cleaning, staff, hiring", "core:forms")


def j_settings(can, d):
    return _link("settings", "Settings", "business, users, payment types", "core:settings")


def j_manual(can, d):
    return _link("manual", "Staff manual", "how to use Pondo", "core:manual")


# key: (name in the list, what it shows, who may have it, on by default, builder)
JOBS = {  # in the same order as the menu on the left
    # Freight & Logistics
    "deliveries": ("Deliveries", "How many orders are out with drivers and the money still to come back",
                   lambda c: c.deliveries_view, True, j_deliveries),
    # Procurement
    "orders": ("Orders on the way", "Orders sent to suppliers and not received yet", lambda c: c.stock_view, False, j_orders),
    "new_order": ("New supplier order", "Quick way to order stock from a supplier", lambda c: c.stock_edit, False, j_new_order),
    "receiving": ("Receiving", "Quick way to type goods in from suppliers (GRV)", lambda c: c.stock_view, True, j_receiving),
    "suppliers": ("Suppliers", "Supplier names, contacts and account numbers", lambda c: c.stock_view, False, j_suppliers),
    "ingredients": ("Ingredients", "Ingredient list, pack sizes and buying prices", lambda c: c.ingredients_view, False, j_ingredients),
    # Inventory
    "low_stock": ("Low stock", "How many items are below the re-order level", lambda c: c.stock_view, False, j_low_stock),
    "stocktake": ("Stock take", "Due when the last stock take is a week old", lambda c: c.stock_view, False, j_stocktake),
    "waste": ("Waste log", "Done when yesterday's waste is written down", lambda c: c.waste_view, True, j_waste),
    "waste_now": ("Write off waste", "Quick way to type waste as it happens", lambda c: c.waste_edit, False, j_waste_now),
    "equipment": ("Equipment count", "Done when this month's equipment count is in", lambda c: c.equipment_view, False, j_equipment),
    # Finance
    "money": ("Cash book", "Money & accounts: safe, bank and EcoCash", lambda c: c.money_view, False, j_money),
    "pay_suppliers": ("Pay suppliers", "What we owe suppliers, and paying them", lambda c: c.money_edit, False, j_pay_suppliers),
    "vat": ("VAT", "This month's VAT", lambda c: c.money_view, False, j_vat),
    "expenses": ("Expenses", "Today's expenses and pay-outs", lambda c: c.sales_view, False, j_expenses),
    "accountant": ("Accountant report", "The full month report for the accountant – last month's in the first 10 days",
                   lambda c: c.costs, True, j_accountant),
    "month_end": ("Month-end report", "Days to month end, opens the month-end report", lambda c: c.costs, False, j_month_end),
    "stock_results": ("Stock results", "The real GP from the stock takes", lambda c: c.costs, False, j_stock_results),
    "gp_check": ("GP check", "Products below 50% gross profit, ready to adjust prices", lambda c: c.costs, False, j_gp_check),
    "excel": ("Excel downloads", "Lists and reports to open in Excel", lambda c: True, False, j_excel),
    # Production
    "plan": ("Production plan", "Done when there is a plan for the day", lambda c: c.production_view, True, j_plan),
    "recipes": ("Recipes", "Recipe list, method, ingredients, recipe cards", lambda c: c.recipes_view, False, j_recipes),
    "price_change": ("Change prices", "Opens Products & Prices ready to type new selling prices",
                     lambda c: c.prices_edit, True, j_price_change),
    "prices": ("Price cards", "Quick way to print shelf cards and posters", lambda c: c.prices_view, True, j_prices),
    # Tax & Compliance
    "fiscal": ("Fiscal (ZIMRA)", "Slips waiting to go to ZIMRA or refused by ZIMRA", lambda c: c.sales_edit, True, j_fiscal),
    "zwg_rate": ("ZWG rate", "Today's ZWG rate – opens Settings to change it", lambda c: c.owner, True, j_zwg_rate),
    # HR
    "payroll": ("Payroll", "This month's pay run – done when it is final", lambda c: c.staff_view, True, j_payroll),
    "add_staff": ("Add staff", "Quick way to add a new person to Staff & Payroll", lambda c: c.staff_edit, True, j_add_staff),
    "staff_list": ("Staff list", "Everybody's details, leave and advances", lambda c: c.staff_view, False, j_staff_list),
    "staff_papers": ("Staff papers", "Only shows when a passport, permit or medical certificate runs out",
                     lambda c: c.staff_view, True, j_staff_papers),
    "sops": ("SOP file", "How we do things – read and sign off", lambda c: c.sops_view, False, j_sops),
    "exams": ("SOP exams", "Test what staff know", lambda c: c.owner, False, j_exams),
    # Administration
    "letters": ("New letter", "Quick way to type a letter on the letterhead", lambda c: c.letters_edit, False, j_letters),
    "forms": ("Blank forms", "Food safety, cleaning, staff and hiring forms to print", lambda c: True, False, j_forms),
    "settings": ("Settings", "Business settings, users and payment types", lambda c: c.owner, False, j_settings),
    "manual": ("Staff manual", "How to use Pondo", lambda c: True, False, j_manual),
    "backup": ("Back up", "Shows when today's cash-ups are not on the flash drive yet", lambda c: c.backup, True, j_backup),
    # Sales
    "till": ("Till", "Which tills are open and who is on them – opens the till", lambda c: c.sales_edit, True, j_till),
    "sales": ("Type the day's sales", "Done when the day's sales from the till are typed", lambda c: c.sales_edit, True, j_sales),
    "cashup": ("Cash-up", "Done when a till is cashed up; shows cash-ups to sign off", lambda c: c.sales_view, True, j_cashup),
    "sales_report": ("Sales report", "Sales per day, week and month", lambda c: c.sales_view, False, j_sales_report),
    "invoices": ("Unpaid invoices", "Tax invoices not paid yet, and how many are overdue", lambda c: c.invoices_view, False, j_invoices),
    "new_invoice": ("New invoice", "Quick way to make a tax invoice", lambda c: c.invoices_edit, False, j_new_invoice),
    "quotes": ("Open quotations", "Quotations still waiting for the customer", lambda c: c.invoices_view, False, j_quotes),
    "new_quote": ("New quotation", "Quick way to make a quotation", lambda c: c.invoices_edit, False, j_new_quote),
    "customers": ("Customers", "Customer list with TIN and VAT numbers", lambda c: c.invoices_view, False, j_customers),
}


# ----------------------------------------------------------------- choosing
def my_jobs_for(user):
    """Jobs this person added, plus jobs somebody added for everybody."""
    from django.db.models import Q

    from .models import MyJob

    if user is None or not user.is_authenticated:
        return []
    return list(MyJob.objects.filter(Q(user=user) | Q(shared=True)).select_related("user"))


def available(can, user):
    """Every job this person may put on the dashboard: [(key, name, about, kind, myjob)]."""
    out = [(k, v[0], v[1], "program", None) for k, v in JOBS.items() if v[2](can)]
    for mj in my_jobs_for(user):
        who = "for everybody" if mj.shared else "your own"
        out.append((mj.key, mj.title, f"{who} · {mj.days_text}" + (f" · {mj.note}" if mj.note else ""), "mine", mj))
    return out


def standard(can, user):
    keys = [k for k, v in JOBS.items() if v[2](can) and v[3]]
    return keys + [mj.key for mj in my_jobs_for(user)]


def saved_order(user):
    """What this person saved: [(key, on)] in their order – or None if they never chose."""
    from .models import UserLook

    look = UserLook.objects.filter(user=user).first() if user is not None and user.is_authenticated else None
    if not look or not look.jobs.strip():
        return None
    return [(k.lstrip("!"), not k.startswith("!")) for k in look.jobs.split(",") if k.strip("!")]


def chosen(can, user):
    """The keys of the jobs this person wants, in their order."""
    saved = saved_order(user)
    if saved is None:
        return standard(can, user)
    allowed = {k for k, *_ in available(can, user)}
    keys = [k for k, on in saved if on and k in allowed]
    seen = {k for k, _ in saved}
    # jobs that are new since this person chose (a new job in the program, or one added for everybody): show them,
    # a new program job next to the job that follows it in the program's list (Change prices just before Price cards)
    program = list(JOBS)
    for k in standard(can, user):
        if k in seen or k not in allowed:
            continue
        later = program[program.index(k) + 1:] if k in JOBS else []
        pos = next((keys.index(x) for x in later if x in keys), None)
        if pos is None:
            keys.append(k)
        else:
            keys.insert(pos, k)
    return keys


def _my_tile(mj, d, done_ids):
    done = mj.pk in done_ids
    url = ""
    if mj.link in ITEMS:
        try:
            url = reverse(ITEMS[mj.link][1])
        except NoReverseMatch:
            url = ""
    art = {"orange": "donut", "teal": "cookie", "burgundy": "pie", "warm": "bread"}.get(mj.colour, "donut")
    return {"area": "mine", "colour": mj.colour, "art": art, "ink": "burgundy" if mj.colour == "warm" else "cream",
            "icon": ICONS.get(mj.link, CHECK) if mj.link else CHECK, "title": mj.title,
            "sub": mj.note or ("for everybody" if mj.shared else "your own job"), "url": url, "done": done,
            "label": "✓ Done" if done else "To do", "my": mj}


def todays_jobs(can, d, backup_due=False, user=None):
    from .models import MyJobDone

    keys = chosen(can, user) if user is not None else standard(can, user)
    mine = {mj.key: mj for mj in my_jobs_for(user)} if user is not None else {}
    done_ids = set(MyJobDone.objects.filter(date=d, job__in=mine.values()).values_list("job_id", flat=True)) if mine else set()
    jobs = []
    for k in keys:
        if k in JOBS:
            fn = JOBS[k][4]
            j = fn(can, d, backup_due) if k == "backup" else fn(can, d)
            if j:
                j["key"] = k
                jobs.append(j)
        elif k in mine and str(d.weekday()) in mine[k].days:
            j = _my_tile(mine[k], d, done_ids)
            j["key"] = k
            jobs.append(j)
    return jobs
