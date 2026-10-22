"""Deliveries: an order taken to a customer by a driver (usually inDrive).

1. New delivery: the customer, the goods, the driver (name, cell, car registration, make, colour) and the fee the
   driver asked. The program makes a tax invoice: goods + delivery fee.
2. Print the invoice and the delivery note (one copy for the driver, one stays at the bakery).
3. The driver collects the money, keeps the fee and brings back the money for the goods.
4. Money back: count it, ring the goods up on the till, type the till slip number. The program checks the money
   against the invoice (short / over) and marks the invoice paid.
"""
import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need
from core.models import log_change
from costing.calc import Calculator
from costing.models import Recipe

from .forms import DeliveryCustomerForm, DeliveryForm, LineFormSet, MoneyBackForm
from .models import Customer, Delivery, DocLine, Document, Driver

Z = Decimal("0")
CUSTOMER_FIELDS = ["name", "company", "address1", "address2", "phone", "email", "vat_no"]


def out_summary():
    """Deliveries still out: how many, and how much money the drivers still have to bring back."""
    out = list(Delivery.objects.filter(status=Delivery.OUT))
    return {"n": len(out), "back": sum((d.expected_back for d in out), Z)}


@need("deliveries")
def delivery_list(request):
    show = request.GET.get("show", "open")
    q = request.GET.get("q", "").strip()
    qs = Delivery.objects.select_related("doc", "created_by", "driver")
    if show == "open":
        qs = qs.filter(status=Delivery.OUT)
    elif show in (Delivery.DONE, Delivery.CANCELLED):
        qs = qs.filter(status=show)
    if q:
        qs = qs.filter(Q(doc__name__icontains=q) | Q(driver_name__icontains=q) | Q(car_reg__icontains=q.replace(" ", ""))
                       | Q(car_reg__icontains=q) | Q(doc__phone__icontains=q) | Q(doc__address1__icontains=q))
    today = timezone.localdate()
    month = today.replace(day=1)
    done_today = Delivery.objects.filter(status=Delivery.DONE, done_at__date=today)
    month_done = Delivery.objects.filter(status=Delivery.DONE, date__gte=month)
    return render(request, "invoices/deliveries.html", {
        "rows": qs[:300], "show": show, "q": q, "out": out_summary(), "today": today,
        "done_today": done_today.count(), "back_today": done_today.aggregate(s=Sum("rung_up"))["s"] or Z,
        "month_n": month_done.count(), "month_goods": month_done.aggregate(s=Sum("goods"))["s"] or Z,
        "month_fees": month_done.aggregate(s=Sum("fee"))["s"] or Z})


def _drivers():
    """The drivers on the list – picking one fills in his cell and car."""
    return {str(d.pk): {"name": d.name, "phone": d.phone, "car_reg": d.car_reg, "car_make": d.car_make,
                        "car_colour": d.car_colour} for d in Driver.objects.filter(active=True)}


def _link_driver(dv):
    """Every delivery is linked to a driver on the drivers list – a new name makes a new driver."""
    drv = dv.driver
    if drv is None:
        name = " ".join(dv.driver_name.split())
        drv = (Driver.objects.filter(name__iexact=name).first()
               or (Driver.objects.filter(phone=dv.driver_phone).first() if dv.driver_phone else None))
        if drv is None:
            drv = Driver.objects.create(name=name, phone=dv.driver_phone, car_reg=dv.car_reg, car_make=dv.car_make,
                                        car_colour=dv.car_colour, issued=dv.date)
            dv._new_driver = True
        dv.driver = drv
    changed = False
    for a, b in (("phone", "driver_phone"), ("car_reg", "car_reg"), ("car_make", "car_make"), ("car_colour", "car_colour")):
        v = getattr(dv, b)
        if v and getattr(drv, a) != v:  # the car he came with this time
            setattr(drv, a, v)
            changed = True
    if changed:
        drv.save()


@need("deliveries", EDIT)
def delivery_edit(request, pk=None):
    dl = get_object_or_404(Delivery.objects.select_related("doc"), pk=pk) if pk else None
    if dl and dl.status != Delivery.OUT:
        messages.error(request, "This delivery is finished – open it again first if it must change.")
        return redirect("invoices:delivery", pk=dl.pk)
    src = None
    if not dl and request.GET.get("from"):
        src = Document.objects.filter(pk=request.GET["from"]).first()
        if src and hasattr(src, "delivery"):
            return redirect("invoices:delivery", pk=src.delivery.pk)
    # the invoice to use: the delivery's own, an open invoice it starts from, or a new one
    if dl:
        doc = dl.doc
    elif src and src.kind == Document.INVOICE and src.status == Document.OPEN:
        doc = src
    else:
        doc = Document(kind=Document.INVOICE, prepared_by=request.user.first_name or request.user.username)
    if request.method == "POST":
        cform = DeliveryCustomerForm(request.POST, instance=doc, prefix="c")
        dform = DeliveryForm(request.POST, instance=dl or Delivery(), prefix="d")
        fs = LineFormSet(request.POST, prefix="ln")
        if cform.is_valid() and dform.is_valid() and fs.is_valid():
            lines = [f.cleaned_data for f in fs.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")
                     and not f.cleaned_data.get("empty")]
            if not lines:
                messages.error(request, "Add the products that go with the driver.")
            else:
                calc = Calculator()
                with transaction.atomic():
                    d = cform.save(commit=False)
                    if d.customer:
                        for f in CUSTOMER_FIELDS:
                            if not getattr(d, f):
                                setattr(d, f, getattr(d.customer, f))
                    elif cform.cleaned_data.get("save_customer") and d.name:
                        d.customer = Customer.objects.create(**{f: getattr(d, f) for f in CUSTOMER_FIELDS})
                    d.kind = Document.INVOICE
                    if not d.created_by_id:
                        d.created_by = request.user
                    dv = dform.save(commit=False)
                    dv.pay = Delivery.DRIVER  # deliveries are cash only
                    _link_driver(dv)
                    d.date = d.due = dv.date
                    if not d.notes:
                        d.notes = "Cash on delivery only – please pay the driver in cash."
                    if src and src.pk != d.pk and not d.from_doc_id:
                        d.from_doc = src
                    d.save()
                    d.lines.all().delete()
                    n = 0
                    for n, cd in enumerate(lines, 1):
                        r = cd["recipe"]
                        DocLine.objects.create(doc=d, recipe=r, description=cd["description"], qty=cd["qty"],
                                               price=cd["price"], discount=cd["discount"], position=n,
                                               vat_rate=calc.vat(r) if r else calc.settings.vat_rate)
                    goods = sum((ln.total for ln in d.lines.all()), Z)
                    if dv.fee:
                        DocLine.objects.create(doc=d, description=f"Delivery fee – paid to the driver ({dv.driver_name}, {dv.car_reg})",
                                               qty=1, price=dv.fee, vat_rate=Z, position=n + 1, is_fee=True)
                    d.refresh_totals()
                    dv.doc, dv.goods = d, goods
                    if not dv.created_by_id:
                        dv.created_by = request.user
                    dv.save()
                    if src and src.kind == Document.QUOTE and src.status == Document.OPEN:
                        src.status = Document.ACCEPTED
                        src.save(update_fields=["status"])
                log_change(request.user, "Deliveries", dv.number, "changed" if pk else "sent",
                           f"{d.name} · {dv.driver_name} {dv.car_reg} · goods ${goods} + fee ${dv.fee}")
                messages.success(request, f"Delivery {dv.number} saved with invoice {d.number}: the customer pays the driver "
                                          f"${dv.total:,.2f} cash, the driver brings back ${dv.expected_back:,.2f}."
                                 + (f" {dv.driver.name} is new on the drivers list – add his photo and print his ID card."
                                    if getattr(dv, "_new_driver", False) else ""))
                return redirect("invoices:delivery", pk=dv.pk)
    else:
        initial_c, initial_lines = {}, []
        base = dl.doc if dl else src
        if base:
            initial_lines = [{"product": ln.description, "qty": ln.qty.normalize(), "price": ln.price,
                              "discount": (ln.discount * 100).normalize() if ln.discount else None}
                             for ln in base.lines.all() if not ln.is_fee]
            if src and not dl:
                initial_c = {"customer": src.customer_id, "your_ref": src.your_ref,
                             **{f: getattr(src, f) for f in CUSTOMER_FIELDS}}
        else:
            c = Customer.objects.filter(pk=request.GET.get("customer") or 0).first()
            if c:
                initial_c = {"customer": c.pk, **{f: getattr(c, f) for f in CUSTOMER_FIELDS}}
        cform = DeliveryCustomerForm(instance=doc, prefix="c", initial=initial_c)
        new = Delivery(date=timezone.localdate(), fee=None)
        drv = Driver.objects.filter(pk=request.GET.get("driver") or 0, active=True).first()
        if drv and not dl:
            new.driver, new.driver_name, new.driver_phone = drv, drv.name, drv.phone
            new.car_reg, new.car_make, new.car_colour = drv.car_reg, drv.car_make, drv.car_colour
        dform = DeliveryForm(instance=dl or new, prefix="d")
        dform.fields["fee"].widget.attrs["placeholder"] = "e.g. 3.00"
        fs = LineFormSet(prefix="ln", initial=initial_lines)
    prices = {r.name: float(r.sell_price) for r in Recipe.objects.filter(active=True, sell_price__isnull=False)}
    customers = {c.pk: {f: getattr(c, f) for f in CUSTOMER_FIELDS} for c in Customer.objects.filter(active=True)}
    names = Recipe.objects.filter(active=True, is_subrecipe=False).order_by("name").values_list("name", flat=True)
    return render(request, "invoices/delivery_form.html", {
        "dl": dl, "src": src, "cform": cform, "dform": dform, "fs": fs, "names": names, "prices": prices,
        "customers": customers, "drivers": _drivers()})


@need("deliveries")
def delivery_detail(request, pk):
    dl = get_object_or_404(Delivery.objects.select_related("doc", "created_by", "checked_by", "driver"), pk=pk)
    form = MoneyBackForm(delivery=dl, initial={"rung_up": dl.goods, "money_back": None})
    return render(request, "invoices/delivery_detail.html", {
        "dl": dl, "doc": dl.doc, "goods_lines": [ln for ln in dl.doc.lines.all() if not ln.is_fee], "form": form})


@need("deliveries", EDIT)
@require_POST
def delivery_status(request, pk):
    dl = get_object_or_404(Delivery.objects.select_related("doc"), pk=pk)
    doc = dl.doc
    to = request.POST.get("to")
    now = timezone.now()
    if to == "delivered" and dl.status == Delivery.OUT:
        dl.delivered_at = now
        dl.save(update_fields=["delivered_at"])
        log_change(request.user, "Deliveries", dl.number, "delivered")
        messages.success(request, f"{dl.number} delivered." + (f" Now wait for ${dl.expected_back:,.2f} from the driver."
                                                               if dl.by_driver else ""))
    elif to == "back" and dl.status == Delivery.OUT:
        form = MoneyBackForm(request.POST, delivery=dl)
        if not form.is_valid():
            messages.error(request, "Not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
            return redirect("invoices:delivery", pk=pk)
        cd = form.cleaned_data
        with transaction.atomic():
            dl.money_back = cd.get("money_back") if dl.by_driver else None
            dl.rung_up, dl.till_ref, dl.back_note = cd["rung_up"], cd["till_ref"], cd["back_note"]
            dl.status, dl.done_at, dl.checked_by = Delivery.DONE, now, request.user
            dl.delivered_at = dl.delivered_at or now
            dl.save()
            if dl.pay != Delivery.ACCOUNT:
                doc.status, doc.paid_on = Document.PAID, timezone.localdate()
                doc.paid_how = Delivery.PAY_SHORT[dl.pay]
                doc.save(update_fields=["status", "paid_on", "paid_how"])
        diff = dl.difference
        rung_diff = dl.rung_up - dl.goods
        note = ""
        if diff:
            note = f" The driver is {'short' if diff < 0 else 'over'} by ${abs(diff):,.2f} – sort it out with the driver."
        if rung_diff:
            note += f" The till has ${abs(rung_diff):,.2f} {'less' if rung_diff < 0 else 'more'} than the goods on the invoice."
        log_change(request.user, "Deliveries", dl.number, "money back",
                   f"back ${dl.money_back} · till ${dl.rung_up} slip {dl.till_ref}" + (f" · diff {diff}" if diff else ""))
        (messages.warning if note else messages.success)(request, f"{dl.number} checked off." + (note or " Everything balances."))
    elif to == "cancel" and dl.status == Delivery.OUT:
        dl.status, dl.done_at, dl.checked_by = Delivery.CANCELLED, now, request.user
        dl.save(update_fields=["status", "done_at", "checked_by"])
        doc.status = Document.CANCELLED
        doc.save(update_fields=["status"])
        log_change(request.user, "Deliveries", dl.number, "cancelled")
        messages.success(request, f"{dl.number} cancelled, and invoice {doc.number} with it.")
    elif to == "reopen" and dl.status != Delivery.OUT:
        dl.status, dl.done_at, dl.checked_by, dl.money_back, dl.rung_up = Delivery.OUT, None, None, None, None
        dl.save()
        doc.status, doc.paid_on, doc.paid_how = Document.OPEN, None, ""
        doc.save(update_fields=["status", "paid_on", "paid_how"])
        log_change(request.user, "Deliveries", dl.number, "opened again")
        messages.success(request, f"{dl.number} is open again.")
    return redirect("invoices:delivery", pk=pk)


@need("deliveries")
def delivery_note(request, pk):
    dl = get_object_or_404(Delivery.objects.select_related("doc", "driver"), pk=pk)
    return render(request, "invoices/delivery_note.html", {
        "dl": dl, "doc": dl.doc, "goods_lines": [ln for ln in dl.doc.lines.all() if not ln.is_fee],
        "copies": ["Driver's copy – goes with the order", "Bakery copy – stays at the till"]})


def deliveries_on(day):
    """Deliveries checked off on one day – their money is in the till (for the cash-up)."""
    return list(Delivery.objects.filter(status=Delivery.DONE, done_at__date=day).select_related("doc"))
