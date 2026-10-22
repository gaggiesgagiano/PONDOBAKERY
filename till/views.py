"""The Pondo till: open a till, sell, take payment, print the receipt, refund, close the till."""
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate  # noqa: F401
from core.cards import approver as card_approver
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import DEFAULT_ROLE, EDIT, need, rights
from core.models import log_change
from costing.calc import Calculator, CycleError
from costing.models import Recipe
from sales.models import CashUp, CashUpLine, Expense, ExpenseCategory, PaymentMethod

from .models import Sale, SaleItem, SalePayment, Shift, Till, TillMovement, zwg_line

FISCAL_TODO = "Not fiscalised yet."


def _fiscal_start():
    """The fiscal status a new slip starts with: 'failed' until the engine has it, so it can never be forgotten."""
    from fiscal import service as fiscal

    return ("failed", FISCAL_TODO) if fiscal.active() else ("practice", "")


def _fiscalise(sale, user):
    """Make the ZIMRA receipt for a slip that is already saved. A problem here never undoes the sale."""
    from fiscal import service as fiscal

    if sale.fiscal_status == "practice":
        return sale
    try:
        return fiscal.fiscalise(sale, user)
    except Exception as e:  # noqa: BLE001
        Sale.objects.filter(pk=sale.pk).update(fiscal_status="failed", fiscal_message=f"Pondo error while fiscalising: {e}")
        sale.fiscal_status, sale.fiscal_message = "failed", f"Pondo error while fiscalising: {e}"
        return sale

Z = Decimal("0")
C = Decimal("0.01")
SMALL_REFUND = Decimal("5")          # SOP 6.02: up to US$5 the Supervisor may approve, more needs a manager
DEFAULT_FLOAT = Decimal("200")       # SOP 2.01 – a fresh float from the safe for every shift
DROP_AT = Decimal("500")             # SOP 2.02 – call the manager for a cash drop above this


def zwg_rate():
    """ZWG per US$1 from Settings – every till uses it for every sale from the moment the Manager saves it."""
    from core.models import CompanySettings

    r = CompanySettings.get().zwg_rate
    return r if r and r > 0 else None


def _method_label(m):
    """'Cash (US$)' -> 'Cash': the currency is chosen separately on the payment screen."""
    return m.name.replace("(US$)", "").replace("(USD)", "").strip()


CUSTOMER_FIELDS = ("customer_name", "customer_tin", "customer_vat", "customer_address", "customer_email", "customer_phone")


def _customer_choices():
    """Saved customers (from Invoices) the cashier can pick on the payment screen."""
    from invoices.models import Customer

    out = []
    for c in Customer.objects.filter(active=True).order_by("name")[:1000]:
        out.append({"id": c.pk, "name": c.company or c.name, "tin": c.tin, "vat": c.vat_no,
                    "address": ", ".join(x for x in (c.address1, c.address2) if x), "email": c.email, "phone": c.phone})
    return out


def _customer(data):
    """The customer's details from the payment screen (all optional). Returns (fields, customer, error)."""
    from invoices.models import Customer

    c = data.get("customer") or {}
    if not isinstance(c, dict):
        return {}, None, None
    clean = lambda k, n: " ".join(str(c.get(k) or "").split())[:n]
    f = {"customer_name": clean("name", 150), "customer_tin": clean("tin", 20).replace(" ", ""),
         "customer_vat": clean("vat", 20).replace(" ", ""), "customer_address": clean("address", 250),
         "customer_email": clean("email", 120), "customer_phone": clean("phone", 40)}
    if not any(f.values()):
        return {}, None, None
    if not f["customer_name"]:
        return f, None, "Customer details: type the name & surname or the business name."
    if f["customer_tin"] and not (f["customer_tin"].isdigit() and len(f["customer_tin"]) == 10):
        return f, None, "Customer details: a TIN number has 10 digits."
    if f["customer_vat"] and not (f["customer_vat"].isdigit() and len(f["customer_vat"]) == 9):
        return f, None, "Customer details: a VAT number has 9 digits."
    if f["customer_email"] and ("@" not in f["customer_email"] or "." not in f["customer_email"].split("@")[-1]):
        return f, None, "Customer details: check the e-mail address."
    cust = Customer.objects.filter(pk=c.get("id")).first() if str(c.get("id") or "").isdigit() else None
    if cust is None and c.get("save"):
        cust = Customer.objects.create(name=f["customer_name"], tin=f["customer_tin"], vat_no=f["customer_vat"],
                                       address1=f["customer_address"][:150], email=f["customer_email"], phone=f["customer_phone"])
    elif cust is not None and f["customer_tin"] and not cust.tin:
        cust.tin = f["customer_tin"]
        cust.save(update_fields=["tin"])
    return f, cust, None


def _dec(v, default=None):
    if v in (None, ""):
        return default
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default


def _today():
    return timezone.localdate()


def _my_shift(request, pk):
    sh = get_object_or_404(Shift.objects.select_related("till", "cashier"), pk=pk)
    if sh.cashier_id != request.user.id and not rights(request).owner:
        raise Http404
    return sh


def _role(user):
    if user.is_superuser:
        return "owner"
    acc = getattr(user, "access", None)
    return (acc.role if acc and acc.role else DEFAULT_ROLE)


def _is_manager(user):
    return _role(user) in ("owner", "assistant_manager", "manager")


def _is_supervisor(user):
    return _role(user) in ("owner", "supervisor", "assistant_manager", "manager")


def cash_in_drawer(sh):
    """US$ the drawer should hold now (ZiG counted in $): float + cash taken − drops − pay-outs."""
    cash = sum((p.amount for p in SalePayment.objects.filter(sale__shift=sh, method__is_cash=True)), Z)
    out = sum((m.amount for m in sh.movements.filter(kind__in=(TillMovement.DROP, TillMovement.PAYOUT))), Z)
    return sh.opening_float + cash - out


def _may_approve(user, amount):
    role = _role(user)
    if role == "owner":
        return True
    if abs(amount) <= SMALL_REFUND:
        return role in ("supervisor", "assistant_manager", "manager")
    return role in ("assistant_manager", "manager")


def _cost(calc, r):
    try:
        return calc.cost_per_unit(r) or Z
    except (CycleError, ZeroDivisionError):
        return Z


def _next_number(till):
    n = Sale.objects.filter(shift__till=till).count() + 1
    while True:
        num = f"{till.code}-{n:05d}"
        if not Sale.objects.filter(number=num).exists():
            return num
        n += 1


def _fiscal_mode():
    """off / test / live – for the badges on the till screens."""
    from fiscal import service as fiscal

    return fiscal.setup().mode if fiscal.active() else "off"


def _invoice_no():
    """The invoice number on the slip and at ZIMRA: YYYYMMDDHHMMSS (the moment of the sale)."""
    return timezone.localtime().strftime("%Y%m%d%H%M%S")


def _give_invoice_no(sale):
    """Give a just-saved slip its invoice number. Two tills in the same second: the later one gets -2, -3 …
    (ZIMRA refuses an invoice number that was used before)."""
    base = _invoice_no()
    num, n = base, 1
    while Sale.objects.filter(fiscal_ref=num).exclude(pk=sale.pk).exists():
        n += 1
        num = f"{base}-{n}"
    sale.fiscal_ref = num
    Sale.objects.filter(pk=sale.pk).update(fiscal_ref=num)


def _safe_back(request):
    b = request.GET.get("back") or ""
    return b if b.startswith("/") and not b.startswith("//") else ""


# ======================================================================= open a till
@need("sales", EDIT)
def start(request):
    today = _today()
    tills = list(Till.objects.filter(active=True))
    todays = list(Shift.objects.filter(date=today).select_related("cashier", "till", "cashup"))
    open_on = {s.till_id: s for s in todays if s.is_open}
    mine = next((s for s in Shift.objects.filter(cashier=request.user, closed_at__isnull=True).select_related("till")), None)
    if request.method == "POST":
        till = get_object_or_404(Till, pk=request.POST.get("till"), active=True)
        sh = open_on.get(till.pk)
        if sh:
            if sh.cashier_id == request.user.id or rights(request).owner:
                return redirect("till:screen", pk=sh.pk)
            messages.error(request, f"{till} is open for {sh.cashier_name()} – they must close it first.")
            return redirect("till:start")
        if mine:
            messages.error(request, f"You still have {mine.till} open. Close it first.")
            return redirect("till:start")
        flt = _dec(request.POST.get("float"), DEFAULT_FLOAT)
        rate = zwg_rate()   # kept on the shift for the record; sales always use the rate in Settings
        if flt is None or flt < 0:
            messages.error(request, "Check the float.")
            return redirect("till:start")
        n = (Shift.objects.filter(till=till, date=today).order_by("-number").values_list("number", flat=True).first() or 0) + 1
        sh = Shift.objects.create(till=till, date=today, number=n, cashier=request.user, opening_float=flt.quantize(C),
                                  zig_rate=rate, float_checked_by=(request.POST.get("checked_by") or "")[:80])
        log_change(request.user, "Till", str(sh), "opened", f"float ${flt}")
        return redirect("till:screen", pk=sh.pk)
    last_rate = zwg_rate()
    rows = [{"till": t, "open": open_on.get(t.pk), "done": [s for s in todays if s.till_id == t.pk and not s.is_open]} for t in tills]
    return render(request, "till/start.html", {"rows": rows, "mine": mine, "today": today, "float": DEFAULT_FLOAT,
                                               "fiscal_mode": _fiscal_mode(),
                                               "zig_rate": last_rate,
                                               "recent": Shift.objects.select_related("till", "cashier")[:20]})


# ======================================================================= the sales screen
@need("sales", EDIT)
def screen(request, pk):
    sh = _my_shift(request, pk)
    if not sh.is_open:
        messages.info(request, f"{sh.till} is closed for today.")
        return redirect("till:start")
    prods = (Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__gt=0)
             .select_related("category").order_by("category__sort_order", "category__name", "name"))
    cats, products = [], []
    for r in prods:
        cat = r.category.name if r.category_id else "Other"
        if cat not in cats:
            cats.append(cat)
        products.append({"id": r.pk, "plu": str(r.number or ""), "name": r.name, "price": str(r.sell_price),
                         "cat": cat, "kg": r.sold_per == "kg", "vat": str(r.vat_rate or 0),
                         "photo": r.photo.url if r.photo else ""})
    methods = [{"id": m.pk, "name": _method_label(m), "cash": m.is_cash,
                "ref": "ecocash" in m.name.lower(), "card": not m.is_cash}
               for m in PaymentMethod.objects.filter(active=True)]
    sold = sh.sales.filter(kind=Sale.SALE)
    return render(request, "till/screen.html", {
        "shift": sh, "cats": cats, "products_json": json.dumps(products), "methods_json": json.dumps(methods),
        "zig_rate": zwg_rate() or "", "n_sales": sold.count(), "drawer": cash_in_drawer(sh), "drop_at": DROP_AT,
        "fiscal_mode": _fiscal_mode(), "customers_json": json.dumps(_customer_choices()),
        "takings": sum((s.total for s in sh.sales.all()), Z)})


@need("sales", EDIT)
@require_POST
def sell(request, pk):
    sh = _my_shift(request, pk)
    if not sh.is_open:
        return JsonResponse({"ok": False, "error": "This till is closed."}, status=400)
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "Bad request."}, status=400)
    calc = Calculator().preload()
    lines, total, vat = [], Z, Z
    for it in data.get("items") or []:
        qty = _dec(it.get("qty"))
        r = Recipe.objects.filter(pk=it.get("id"), active=True, is_subrecipe=False, sell_price__gt=0).first()
        if not r or qty is None or qty <= 0 or qty > 999:
            return JsonResponse({"ok": False, "error": "A product on the slip is not valid any more."}, status=400)
        qty = qty.quantize(Decimal("0.001"))
        lt = (qty * r.sell_price).quantize(C)
        lines.append((r, qty, lt))
        total += lt
        vat += lt - lt / (1 + (r.vat_rate or Z))
    if not lines:
        return JsonResponse({"ok": False, "error": "Nothing on the slip."}, status=400)
    cust_fields, cust, cust_err = _customer(data)
    if cust_err:
        return JsonResponse({"ok": False, "error": cust_err, "customer_error": True}, status=400)
    methods = {m.pk: m for m in PaymentMethod.objects.filter(active=True)}
    rate = zwg_rate()
    pays, cash_in, other_in = [], Z, Z
    for p in data.get("payments") or []:
        m = methods.get(int(p.get("method") or 0))
        if not m:
            return JsonResponse({"ok": False, "error": "Choose how the customer pays."}, status=400)
        zig = _dec(p.get("zig"))
        if zig is not None:
            if not rate:
                return JsonResponse({"ok": False, "error": "There is no ZWG rate – the Manager sets it under Settings."}, status=400)
            used = _dec(data.get("rate"))
            if used is not None and used != rate:
                return JsonResponse({"ok": False, "rate": str(rate),
                                     "error": f"The ZWG rate was just changed to {rate.normalize():f} per US$1. "
                                              "Remove the ZWG payment and type it again."}, status=409)
            if zig <= 0:
                return JsonResponse({"ok": False, "error": "An amount is missing."}, status=400)
            amt = (zig / rate).quantize(C)
            room = total - other_in
            if not m.is_cash and room < amt <= room + C:
                amt = room          # ZWG rounding: a card / EcoCash payment of "exact" ZWG may be a cent over
        else:
            amt = _dec(p.get("amount"))
        if amt is None or amt <= 0:
            return JsonResponse({"ok": False, "error": "An amount is missing."}, status=400)
        ref = (p.get("ref") or "").strip()[:80]
        if "ecocash" in m.name.lower() and not ref:
            return JsonResponse({"ok": False, "error": "Type the EcoCash reference from the confirmation message."}, status=400)
        if not m.is_cash and amt > total:
            return JsonResponse({"ok": False, "error": "Card / EcoCash / bank can't be more than the total."}, status=400)
        pays.append({"m": m, "amt": amt.quantize(C), "zig": zig, "ref": ref})
        if m.is_cash:
            cash_in += amt
        else:
            other_in += amt
    fx = {"currency": "USD"}
    if pays and all(p["zig"] is not None for p in pays):
        # paid all in ZWG: the receipt is in ZWG – prices, VAT, total and change (the books stay in US$)
        total_z = sum((zwg_line(r.sell_price, qty, rate) for r, qty, lt in lines), Z)
        vat_z = sum((zwg_line(r.sell_price, qty, rate) - zwg_line(r.sell_price, qty, rate) / (1 + (r.vat_rate or Z))
                     for r, qty, lt in lines), Z).quantize(C)
        cash_z = sum((p["zig"] for p in pays if p["m"].is_cash), Z)
        other_z = sum((p["zig"] for p in pays if not p["m"].is_cash), Z)
        if other_z > total_z + C:
            return JsonResponse({"ok": False, "error": "Card / EcoCash / bank can't be more than the total."}, status=400)
        excess = other_z - total_z               # a card / EcoCash "exact" a cent over is just rounding
        for p in pays:
            if excess > 0 and not p["m"].is_cash:
                cut = min(excess, p["zig"])
                p["zig"] -= cut
                excess -= cut
        other_z = min(other_z, total_z)
        if cash_z + other_z < total_z - C:     # one cent of rounding is let go
            return JsonResponse({"ok": False, "error": f"Still to pay: ZWG {total_z - cash_z - other_z:,.2f}"}, status=400)
        change_z = max(cash_z + other_z - total_z, Z)
        if change_z > cash_z:
            return JsonResponse({"ok": False, "error": "Change can only be given from cash."}, status=400)
        change = (change_z / rate).quantize(C)
        fx = {"currency": "ZWG", "fx_rate": rate, "total_fx": total_z, "vat_fx": vat_z, "change_fx": change_z}
        # the US$ kept must add up to the US$ total exactly (the cash-up works in US$)
        residue = total - (cash_in + other_in - change)
        if residue:
            pays[-1]["amt"] = (pays[-1]["amt"] + residue).quantize(C)
    else:
        if other_in > total:
            return JsonResponse({"ok": False, "error": "Card / EcoCash can't be more than the total."}, status=400)
        paid = cash_in + other_in
        if paid < total:
            return JsonResponse({"ok": False, "error": f"Still to pay: ${total - paid:,.2f}"}, status=400)
        change = (paid - total).quantize(C)
        if change > cash_in:
            return JsonResponse({"ok": False, "error": "Change can only be given from cash."}, status=400)
    f_status, f_msg = _fiscal_start()
    with transaction.atomic():
        sale = Sale.objects.create(shift=sh, number=_next_number(sh.till), created_by=request.user, total=total,
                                   vat=vat.quantize(C), change=change, fiscal_status=f_status, fiscal_message=f_msg,
                                   customer=cust, **cust_fields, **fx)
        _give_invoice_no(sale)
        for r, qty, lt in lines:
            SaleItem.objects.create(sale=sale, recipe=r, name=r.name, qty=qty, price=r.sell_price,
                                    vat_rate=r.vat_rate or Z, unit_cost=_cost(calc, r), total=lt)
        left = change   # take the change off the cash received – US$ cash first, then ZiG
        for p in sorted(pays, key=lambda p: (not p["m"].is_cash, p["zig"] is not None)):
            keep = p["amt"]
            if p["m"].is_cash and left > 0:
                cut = min(left, keep)
                keep -= cut
                left -= cut
            SalePayment.objects.create(sale=sale, method=p["m"], amount=keep, tendered=p["amt"],
                                       zig_amount=p["zig"], zig_rate=rate if p["zig"] is not None else None,
                                       ref=p["ref"])
    _fiscalise(sale, request.user)
    return JsonResponse({"ok": True, "number": sale.number, "total": str(total), "change": str(change),
                         "currency": sale.currency, "change_fx": str(sale.change_fx or ""),
                         "drawer": str(cash_in_drawer(sh)), "fiscal": sale.fiscal_status,
                         "fiscal_note": _fiscal_note(sale),
                         "receipt": reverse("till:receipt", args=[sale.pk]) + "?print=1"})


def _fiscal_note(sale):
    """One line for the cashier after the sale."""
    if sale.fiscal_status == "submitted":
        return ""
    if sale.fiscal_status == "pending":
        return "ZIMRA not reachable – the slip is signed and waits to be sent. Keep selling."
    if sale.fiscal_status == "flagged":
        return "Signed fiscal slip printed, but ZIMRA flagged it red – the Supervisor checks the Fiscal page."
    if sale.fiscal_status == "failed":
        return "NOT fiscalised: " + (sale.fiscal_message or "")[:220] + " – tell the Supervisor (Fiscal page)."
    return ""


@need("sales")
def receipt(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("shift__till", "shift__cashier", "refund_of"), pk=pk)
    fiscal = {}
    if sale.is_fiscal:
        from fiscal.qr import qr_svg
        from fiscal.service import trader

        code = sale.fiscal_qr.rstrip("/")[-16:].upper()
        fiscal = {"qr": qr_svg(sale.fiscal_qr), "trader": trader(),
                  "code": "-".join(code[i:i + 4] for i in range(0, 16, 4)) if len(code) == 16 else ""}
    lines = sale.lines()        # in the receipt's currency (US$, or ZWG when paid all in ZWG)
    items = [it for it, price, line in lines]
    by_rate = {}
    for it, price, line in lines:   # VAT summary per rate, as on a ZIMRA slip
        r = by_rate.setdefault(it.vat_rate, {"pct": it.vat_rate * 100, "total": Z})
        r["total"] += line
    vat_rows = []
    for r in sorted(by_rate.values(), key=lambda r: -r["pct"]):
        net = (r["total"] / (1 + r["pct"] / 100)).quantize(C)
        pct = r["pct"].normalize()
        vat_rows.append({"pct": format(pct.quantize(Decimal(1)) if pct == pct.to_integral() else pct, "f"), "net": net, "vat": r["total"] - net, "total": r["total"]})
    return render(request, "till/receipt.html", {"sale": sale, "items": items, "lines": lines, "vat_rows": vat_rows,
                                                 "payments": sale.payments.select_related("method"), "fiscal": fiscal,
                                                 "auto": request.GET.get("print") == "1", "back": _safe_back(request)})


@need("sales", EDIT)
def shift_sales(request, pk):
    sh = _my_shift(request, pk)
    sales = sh.sales.prefetch_related("items", "payments__method")
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        sales = sales.filter(Q(number__icontains=q) | Q(fiscal_ref__icontains=q))
    return render(request, "till/sales.html", {"shift": sh, "sales": sales[:300], "q": q})


@need("sales", EDIT)
def refund(request, pk, sale_pk):
    sh = _my_shift(request, pk)
    if not sh.is_open:
        return redirect("till:start")
    sale = get_object_or_404(Sale.objects.select_related("shift__till"), pk=sale_pk, kind=Sale.SALE)
    done = sale.refunded_qty()
    rows = [{"it": it, "left": it.qty - done.get(it.recipe_id, Z)} for it in sale.items.all()]
    methods = PaymentMethod.objects.filter(active=True)
    first = sale.payments.select_related("method").first()
    error = None
    if request.method == "POST":
        back, total = [], Z
        for row in rows:
            q = _dec(request.POST.get(f"q{row['it'].pk}"), Z)
            if q < 0 or q > row["left"]:
                error = f"{row['it'].name}: you can refund at most {row['left']:g}."
                break
            if q:
                lt = (q * row["it"].price).quantize(C)
                back.append((row["it"], q, lt))
                total += lt
        reason = (request.POST.get("reason") or "").strip()[:200]
        m = methods.filter(pk=request.POST.get("method")).first()
        approver = card_approver(request)
        if not error:
            if not back:
                error = "Type how many of each product come back."
            elif not reason:
                error = "Type the reason (SOP: refunds only with a reasonable reason and the till slip)."
            elif not m:
                error = "Choose how the money goes back."
            elif approver is None:
                error = "The Supervisor or Manager must scan their card, or type their own username and password, to approve."
            elif approver.pk == sh.cashier_id and not approver.is_superuser:
                error = "A cashier can't approve their own refund – call the Supervisor."
            elif not _may_approve(approver, total):
                error = (f"Refunds above ${SMALL_REFUND:.0f} need a manager's approval."
                         if total > SMALL_REFUND else "Only a Supervisor or manager can approve refunds.")
        if not error:
            f_status, f_msg = _fiscal_start()
            fx = {"currency": "USD"}
            if sale.in_zwg:   # a ZWG sale is refunded in ZWG, at the rate it was sold at (one currency per credit note)
                tz = sum((zwg_line(it.price, q, sale.fx_rate) for it, q, lt in back), Z)
                vz = sum((zwg_line(it.price, q, sale.fx_rate) - zwg_line(it.price, q, sale.fx_rate) / (1 + it.vat_rate)
                          for it, q, lt in back), Z).quantize(C)
                fx = {"currency": "ZWG", "fx_rate": sale.fx_rate, "total_fx": -tz, "vat_fx": -vz, "change_fx": Z}
            with transaction.atomic():
                rf = Sale.objects.create(shift=sh, number=_next_number(sh.till), kind=Sale.REFUND, created_by=request.user,
                                         total=-total, vat=-sum((lt - lt / (1 + it.vat_rate) for it, q, lt in back), Z).quantize(C),
                                         refund_of=sale, approved_by=approver, reason=reason,
                                         fiscal_status=f_status, fiscal_message=f_msg, customer_id=sale.customer_id,
                                         **{k: getattr(sale, k) for k in CUSTOMER_FIELDS}, **fx)   # same customer
                _give_invoice_no(rf)
                for it, q, lt in back:
                    SaleItem.objects.create(sale=rf, recipe=it.recipe, name=it.name, qty=-q, price=it.price,
                                            vat_rate=it.vat_rate, unit_cost=it.unit_cost, total=-lt)
                SalePayment.objects.create(sale=rf, method=m, amount=-total, tendered=-total,
                                           zig_amount=fx.get("total_fx"), zig_rate=fx.get("fx_rate"))
                if request.POST.get("waste"):
                    _refund_waste(rf, back, request.user)
            log_change(request.user, "Till", rf.number, "refund", f"{sale.number} ${total} – {reason} – approved by {approver}")
            _fiscalise(rf, request.user)
            if rf.fiscal_status == "failed":
                messages.warning(request, f"The refund is saved, but the ZIMRA credit note was refused: {rf.fiscal_message[:200]}")
            messages.success(request, f"Refund {rf.number} done: ${total:,.2f}." + (" Logged as waste (Customer return)."
                             if request.POST.get("waste") else " The products went back on the shelf."))
            return redirect(reverse("till:receipt", args=[rf.pk]) + "?print=1&back=" + reverse("till:screen", args=[sh.pk]))
    return render(request, "till/refund.html", {"shift": sh, "sale": sale, "rows": rows, "methods": methods,
                                                "first": first.method_id if first else None, "error": error,
                                                "post": request.POST if request.method == "POST" else {}})


def _refund_waste(rf, back, user):
    from production.models import WasteLine, WasteLog
    log, _ = WasteLog.objects.get_or_create(date=rf.shift.date, shift="day", defaults={"recorded_by": user})
    for it, q, lt in back:
        WasteLine.objects.create(log=log, recipe=it.recipe, qty=q, reason="Customer return",
                                 notes=f"Till refund {rf.number}", unit_cost=it.unit_cost)


# ======================================================================= cash drop · pay-out · no sale
MOVE_RULES = {
    TillMovement.DROP: ("Cash drop to the safe", _is_manager, "Only a manager (Manager / Assistant Manager) has the safe key – they must approve a cash drop."),
    TillMovement.PAYOUT: ("Pay-out from the till", _is_supervisor, "A Supervisor or manager must approve a pay-out."),
    TillMovement.NOSALE: ("No sale – open the drawer", _is_supervisor, "A Supervisor or manager must approve opening the drawer."),
}


@need("sales", EDIT)
def move(request, pk, kind):
    sh = _my_shift(request, pk)
    if not sh.is_open or kind not in MOVE_RULES:
        return redirect("till:start")
    title, allowed, refuse = MOVE_RULES[kind]
    drawer = cash_in_drawer(sh)
    cats = ExpenseCategory.objects.filter(active=True)
    error = None
    if request.method == "POST":
        amount = _dec(request.POST.get("amount"), Z) if kind != TillMovement.NOSALE else Z
        reason = (request.POST.get("reason") or "").strip()[:200]
        approver = card_approver(request)
        cat = cats.filter(pk=request.POST.get("category")).first()
        if kind != TillMovement.NOSALE and (amount is None or amount <= 0):
            error = "Type the amount."
        elif kind != TillMovement.NOSALE and amount > drawer:
            error = "That is more cash than the till has taken – check the amount."
        elif kind == TillMovement.PAYOUT and not cat:
            error = "Choose what the money was for."
        elif kind != TillMovement.DROP and not reason:
            error = "Type the reason."
        elif approver is None:
            error = "The person approving must scan their card, or type their own username and password."
        elif approver.pk == sh.cashier_id and not approver.is_superuser:
            error = "A cashier can't approve for their own till."
        elif not allowed(approver):
            error = refuse
        if not error:
            with transaction.atomic():
                exp = None
                if kind == TillMovement.PAYOUT:
                    exp = Expense.objects.create(date=sh.date, category=cat, amount=amount.quantize(C), paid_from=Expense.TILL,
                                                 payee=(request.POST.get("payee") or "")[:100], description=reason,
                                                 receipt_no=(request.POST.get("slip") or "")[:60], created_by=request.user)
                mv = TillMovement.objects.create(shift=sh, kind=kind, amount=(amount or Z).quantize(C), reason=reason,
                                                 approved_by=approver, created_by=request.user, expense=exp)
            log_change(request.user, "Till", mv.number, kind, f"{sh.label} ${mv.amount} – {reason} – approved by {approver}")
            return redirect(reverse("till:move_slip", args=[mv.pk]) + "?print=1&back=" + reverse("till:screen", args=[sh.pk]))
    return render(request, "till/move.html", {"shift": sh, "kind": kind, "title": title, "drawer": drawer, "cats": cats,
                                              "error": error, "post": request.POST if request.method == "POST" else {},
                                              "drop_at": DROP_AT})


@need("sales")
def move_slip(request, pk):
    mv = get_object_or_404(TillMovement.objects.select_related("shift__till", "shift__cashier", "approved_by", "expense__category"), pk=pk)
    return render(request, "till/move_slip.html", {"mv": mv, "auto": request.GET.get("print") == "1", "back": _safe_back(request)})


# ======================================================================= close the till
def _shift_totals(sh):
    by = defaultdict(lambda: Z)
    zig = Z
    for p in SalePayment.objects.filter(sale__shift=sh).select_related("method"):
        by[p.method] += p.amount
        if p.zig_amount and p.method.is_cash:
            zig += p.zig_amount
    sales = sh.sales.all()
    return {"by": sorted(by.items(), key=lambda kv: (kv[0].sort_order, kv[0].name)), "zig": zig,
            "total": sum((s.total for s in sales), Z),
            "n": sum(1 for s in sales if s.kind == Sale.SALE), "refunds": [s for s in sales if s.kind == Sale.REFUND],
            "cash": sum((v for m, v in by.items() if m.is_cash), Z)}


@need("sales", EDIT)
def close(request, pk):
    sh = _my_shift(request, pk)
    if not sh.is_open:
        return redirect("till:start")
    t = _shift_totals(sh)
    error = None
    if request.method == "POST":
        counted = _dec(request.POST.get("cash"))
        zig = _dec(request.POST.get("zig"), Z)
        float_left = _dec(request.POST.get("float_left"), sh.opening_float)
        if counted is None or counted < 0 or zig < 0 or float_left is None or float_left < 0:
            error = "Type the cash you counted (notes and coins, float included)."
        elif CashUp.objects.filter(date=sh.date, till__iexact=sh.label).exists():
            error = f"There is already a cash-up for {sh.label} on {sh.date:%d %b} – ask the Manager to check it first."
        if not error:
            with transaction.atomic():
                drops = sum((m.amount for m in sh.movements.filter(kind=TillMovement.DROP)), Z)
                cu = CashUp.objects.create(date=sh.date, till=sh.label, cashier=sh.cashier_name(), drops=drops,
                                           opening_float=sh.opening_float, cash_counted=counted.quantize(C),
                                           zig_counted=zig.quantize(C) if zig else None, zig_rate=zwg_rate() or sh.zig_rate,
                                           float_left=float_left.quantize(C), created_by=request.user,
                                           notes=f"From the Pondo till ({t['n']} sales).")
                used = dict(t["by"])
                for m in PaymentMethod.objects.filter(active=True):
                    if m in used or m.is_cash:
                        CashUpLine.objects.create(cashup=cu, method=m, till_amount=used.get(m, Z).quantize(C))
                Expense.objects.filter(till_movement__shift=sh).update(cashup=cu)
                cu.refresh_totals()
                sh.closed_at, sh.closed_by, sh.cashup = timezone.now(), request.user, cu
                sh.save(update_fields=["closed_at", "closed_by", "cashup"])
                rebuild_day(sh.date, request.user)
            log_change(request.user, "Till", str(sh), "closed", f"sales ${t['total']} · counted ${counted}")
            messages.success(request, f"{sh.label} closed. The Supervisor checks the cash-up and signs it off. "
                                      f"The next shift can re-open {sh.till} with a fresh float.")
            if _fiscal_mode() != "off" and not Shift.objects.filter(closed_at__isnull=True).exists():
                messages.info(request, "That was the last open till. At the end of the day the Supervisor closes the "
                                       "fiscal day on the Fiscal page (Z report).")
            return redirect(reverse("sales:cashup", args=[cu.pk]) + "?saved=1")
    return render(request, "till/close.html", {"shift": sh, "t": t, "error": error,
                                               "moves": sh.movements.select_related("approved_by"),
                                               "expected": sh.opening_float + t["cash"], "post": request.POST})


def rebuild_day(d, user=None):
    """Product sales and category sales of a day, worked out from every till sale of that day."""
    from core.targets import product_gps
    from sales.models import DailySales, DailySalesLine, DaySales, SaleLine

    items = list(SaleItem.objects.filter(sale__shift__date=d).select_related("recipe"))
    if not items:
        return
    per = {}
    for it in items:
        a = per.setdefault(it.recipe_id, {"r": it.recipe, "qty": Z, "value": Z, "cost": Z, "vat": it.vat_rate})
        a["qty"] += it.qty
        a["value"] += it.total
        a["cost"] += it.qty * it.unit_cost
    ds, _ = DaySales.objects.get_or_create(date=d, defaults={"created_by": user})
    ds.notes = "Worked out from the Pondo till."
    ds.save()
    ds.lines.all().delete()
    by_cat = defaultdict(lambda: Z)
    for i, a in enumerate(sorted(per.values(), key=lambda a: -a["value"])):
        if a["qty"] <= 0:
            continue
        SaleLine.objects.create(day=ds, recipe=a["r"], qty=a["qty"].quantize(C), price=(a["value"] / a["qty"]).quantize(C),
                                vat_rate=a["vat"], unit_cost=(a["cost"] / a["qty"]), position=i)
        by_cat[a["r"].category] += a["value"] / (1 + a["vat"])
    cat_gp, avg = product_gps()
    rec, _ = DailySales.objects.get_or_create(date=d, defaults={"created_by": user})
    rec.gp = None
    rec.notes = "Worked out from the Pondo till."
    rec.save()
    rec.lines.all().delete()
    total = gp_amount = Z
    for cat, v in by_cat.items():
        v = v.quantize(C)
        if cat is None or v <= 0:
            continue
        g = cat_gp.get(cat.pk, avg)
        DailySalesLine.objects.create(day=rec, category=cat, amount=v, gp=g)
        total += v
        gp_amount += v * g
    rec.total, rec.gp_amount = total, gp_amount.quantize(C)
    rec.save(update_fields=["total", "gp_amount"])
