from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need, rights
from core.models import log_change
from costing.calc import Calculator
from costing.models import Ingredient, IngredientPriceChange, Recipe, Supplier

from .forms import (CountHeaderForm, GRVForm, GRVLineFormSet, OrderForm, OrderLineFormSet, SupplierForm)
from .levels import last_count, on_hand_all, purchases_between, stock_rows, suggest_packs, usage_mode
from .models import GRV, CountLine, GRVLine, OrderLine, OrderSend, PurchaseOrder, StockCount

Z = Decimal("0")


def _item_names():
    return Ingredient.objects.filter(active=True).exclude(kind=Ingredient.SUBRECIPE).order_by("name").values_list("name", flat=True)


def _num(v):
    return format(v.normalize(), "f") if v is not None else None


# ======================================================================= stock levels
@need("stock")
def stock_home(request):
    sup = request.GET.get("sup", "")
    low = request.GET.get("low") == "1"
    supplier = Supplier.objects.filter(pk=sup).first() if sup else None
    rows, lc = stock_rows(supplier, low)
    total = sum((r["value"] for r in rows), Z)
    n_low = sum(1 for r in rows if r["low"])
    return render(request, "stock/home.html", {"rows": rows, "lc": lc, "total": total, "sup": sup, "low": low,
                                               "n_low": n_low, "suppliers": Supplier.objects.filter(active=True),
                                               "open_orders": PurchaseOrder.objects.filter(status=PurchaseOrder.SENT).count()})


# ======================================================================= suppliers
@need("stock")
def supplier_list(request):
    return render(request, "stock/supplier_list.html", {"suppliers": Supplier.objects.all()})


@need("stock", EDIT)
def supplier_edit(request, pk=None):
    s = get_object_or_404(Supplier, pk=pk) if pk else Supplier()
    form = SupplierForm(request.POST or None, instance=s)
    if request.method == "POST" and form.is_valid():
        s = form.save()
        log_change(request.user, "Suppliers", s.name, "changed" if pk else "added")
        messages.success(request, f"Saved {s.name}.")
        return redirect("stock:suppliers")
    return render(request, "stock/supplier_form.html", {"form": form, "s": s})


# ======================================================================= orders
@need("stock")
def order_list(request):
    orders = PurchaseOrder.objects.select_related("supplier", "ordered_by").prefetch_related("lines")[:150]
    return render(request, "stock/order_list.html", {"orders": orders})


def _save_lines(model, parent_field, parent, fs, extra=None):
    model.objects.filter(**{parent_field: parent}).delete()
    pos = 0
    for f in fs.forms:
        cd = f.cleaned_data
        if not cd or cd.get("DELETE") or cd.get("empty"):
            continue
        pos += 1
        kw = {parent_field: parent, "ingredient": cd["ingredient"], "packs": cd["packs"], "pack_price": cd["pack_price"],
              "position": pos}
        if extra:
            kw.update(extra(cd))
        model.objects.create(**kw)
    return pos


@need("stock", EDIT)
def order_edit(request, pk=None):
    o = get_object_or_404(PurchaseOrder, pk=pk) if pk else PurchaseOrder(ordered_by=request.user)
    if o.pk and o.status in (PurchaseOrder.RECEIVED, PurchaseOrder.CANCELLED):
        messages.error(request, "This order is closed and can't be changed.")
        return redirect("stock:order", pk=o.pk)
    if request.method == "POST":
        form = OrderForm(request.POST, instance=o)
        fs = OrderLineFormSet(request.POST, prefix="ln")
        if form.is_valid() and fs.is_valid():
            with transaction.atomic():
                o = form.save()
                n = _save_lines(OrderLine, "order", o, fs)
            log_change(request.user, "Orders", o.number, "saved", f"{n} lines")
            messages.success(request, f"Order {o.number} saved.")
            return redirect("stock:order", pk=o.pk)
    else:
        sup = Supplier.objects.filter(pk=request.GET.get("supplier")).first()
        form = OrderForm(instance=o, initial={"supplier": sup.pk} if sup else None)
        if o.pk:
            initial = [{"item": ln.ingredient.name, "packs": _num(ln.packs), "pack_price": _num(ln.pack_price)}
                       for ln in o.lines.select_related("ingredient")]
        elif sup:
            # suggest what is low for this supplier
            qty, _ = on_hand_all()
            initial = []
            for i in Ingredient.objects.filter(active=True, supplier=sup).exclude(kind=Ingredient.SUBRECIPE):
                s = suggest_packs(i, qty.get(i.pk, Z))
                if s:
                    initial.append({"item": i.name, "packs": _num(s), "pack_price": _num(i.pack_price)})
            if initial:
                messages.info(request, f"{len(initial)} item(s) are low on stock and were added for you.")
        else:
            initial = []
        fs = OrderLineFormSet(prefix="ln", initial=initial)
    return render(request, "stock/order_form.html", {"form": form, "fs": fs, "o": o, "names": _item_names(),
                                                     "prices": _price_map()})


def _price_map():
    return {i.name: {"price": float(i.pack_price or 0), "size": float(i.pack_size or 0), "unit": i.unit,
                     "sup": i.supplier.name if i.supplier else ""}
            for i in Ingredient.objects.filter(active=True).exclude(kind=Ingredient.SUBRECIPE).select_related("supplier")}


@need("stock")
def order_detail(request, pk):
    o = get_object_or_404(PurchaseOrder.objects.select_related("supplier", "ordered_by"), pk=pk)
    return render(request, "stock/order_detail.html", {"o": o, "lines": o.lines.select_related("ingredient")})


@need("stock")
def order_print(request, pk):
    o = get_object_or_404(PurchaseOrder.objects.select_related("supplier", "ordered_by"), pk=pk)
    return render(request, "stock/print_order.html", {"o": o, "lines": o.lines.select_related("ingredient")})


@need("stock", EDIT)
@require_POST
def order_status(request, pk):
    o = get_object_or_404(PurchaseOrder, pk=pk)
    new = request.POST.get("status")
    if new in (PurchaseOrder.SENT, PurchaseOrder.CANCELLED, PurchaseOrder.DRAFT) and o.status != PurchaseOrder.RECEIVED:
        o.status = new
        o.save()
        log_change(request.user, "Orders", o.number, f"marked {o.get_status_display()}")
    return redirect("stock:order", pk=pk)


COUNTRIES = [("263", "Zimbabwe +263"), ("27", "South Africa +27")]


def wa_number(raw, country="263"):
    """A phone number as WhatsApp wants it: country code + number, digits only.
    Numbers typed with + / 00 / 263 / 27 in front keep their country; local numbers (07…, 082…) get the chosen country."""
    raw = (raw or "").strip()
    d = "".join(ch for ch in raw if ch.isdigit())
    if country not in dict(COUNTRIES):
        country = "263"
    if raw.startswith("+"):
        pass
    elif d.startswith("00"):
        d = d[2:]
    elif d.startswith("0"):
        d = country + d[1:]
    elif (d.startswith("263") and len(d) == 12) or (d.startswith("27") and len(d) == 11):
        pass
    elif len(d) == 9:
        d = country + d
    return d if 10 <= len(d) <= 15 else ""


def guess_country(raw):
    d = "".join(ch for ch in (raw or "") if ch.isdigit())
    return "27" if (raw or "").strip().startswith("+27") or (d.startswith("27") and len(d) == 11) or d.startswith("0027") else "263"


def _sender_name(user):
    if user.is_superuser:
        return "Jurie Gagiano"
    return f"{user.first_name} {user.last_name}".strip() or user.username


def order_message(o, user):
    def n(x):
        x = x.normalize() if hasattr(x, "normalize") else x
        return f"{x:f}".rstrip("0").rstrip(".") if "." in f"{x:f}" else f"{x:f}"
    shop = "Pondo Bakery"
    out = [f"Good day {o.supplier.contact or o.supplier.name}", "",
           f"*Order {o.number}* from {shop}"]
    if o.supplier.account_no:
        out.append(f"Our account no: {o.supplier.account_no}")
    if o.delivery_date:
        out.append(f"Delivery: {o.delivery_date:%A %d %B %Y}")
    out.append("")
    for ln in o.lines.select_related("ingredient"):
        i = ln.ingredient
        out.append(f"• {n(ln.packs)} × {i.name}" + (f" ({n(i.pack_size)} {i.unit})" if i.pack_size else "")
                   + (f" – code {i.code}" if getattr(i, "code", "") else ""))
    if o.notes:
        out += ["", o.notes.strip()]
    out += ["", "Please confirm the order and let us know if anything is out of stock.", "",
            "Thank you", _sender_name(user), shop]
    return "\n".join(out)


@need("stock", EDIT)
def order_whatsapp(request, pk):
    o = get_object_or_404(PurchaseOrder.objects.select_related("supplier"), pk=pk)
    if o.status == PurchaseOrder.CANCELLED:
        messages.error(request, "This order was cancelled.")
        return redirect("stock:order", pk=pk)
    error = ""
    if request.method == "POST":
        number = wa_number(request.POST.get("number"), request.POST.get("country"))
        text = (request.POST.get("text") or "").strip()
        if not number:
            error = "Type the supplier's WhatsApp number, e.g. 0771 234 567, +263 77 123 4567 or +27 82 123 4567."
        elif not text:
            error = "The message is empty."
        else:
            OrderSend.objects.create(order=o, how=OrderSend.WHATSAPP, to="+" + number, by=request.user,
                                     details="Opened in WhatsApp to send")
            if request.POST.get("save_number") and not o.supplier.phone:
                o.supplier.phone = request.POST.get("number").strip()
                o.supplier.save(update_fields=["phone"])
            if request.POST.get("mark_sent") and o.status == PurchaseOrder.DRAFT:
                o.status = PurchaseOrder.SENT
                o.save(update_fields=["status"])
            log_change(request.user, "Orders", o.number, "sent by WhatsApp", "+" + number)
            from urllib.parse import quote
            return redirect(f"https://wa.me/{number}?text={quote(text)}")
    return render(request, "stock/order_whatsapp.html", {
        "o": o, "error": error, "countries": COUNTRIES,
        "country": request.POST.get("country") if request.method == "POST" else guess_country(o.supplier.phone),
        "number": request.POST.get("number", o.supplier.phone) if request.method == "POST" else o.supplier.phone,
        "text": request.POST.get("text") if request.method == "POST" else order_message(o, request.user)})


# ======================================================================= GRV
@need("stock")
def grv_list(request):
    grvs = GRV.objects.select_related("supplier", "order", "received_by").prefetch_related("lines__ingredient")[:150]
    return render(request, "stock/grv_list.html", {"grvs": grvs})


@need("stock", EDIT)
def grv_edit(request, pk=None):
    g = get_object_or_404(GRV, pk=pk) if pk else GRV(received_by=request.user)
    order = g.order
    if not pk and request.GET.get("order"):
        order = get_object_or_404(PurchaseOrder, pk=request.GET["order"])
    if request.method == "POST":
        form = GRVForm(request.POST, instance=g)
        fs = GRVLineFormSet(request.POST, prefix="ln")
        if form.is_valid() and fs.is_valid():
            changed = []
            with transaction.atomic():
                g = form.save(commit=False)
                if order and not g.order_id:
                    g.order = order
                g.save()
                n = _save_lines(GRVLine, "grv", g, fs, extra=lambda cd: {"packs_ordered": cd.get("packs_ordered")})
                if form.cleaned_data.get("update_prices"):
                    for ln in g.lines.select_related("ingredient"):
                        i = ln.ingredient
                        if ln.pack_price and ln.pack_price != i.pack_price:
                            IngredientPriceChange.objects.create(ingredient=i, user=request.user, old_price=i.pack_price,
                                                                 new_price=ln.pack_price, old_pack_size=i.pack_size,
                                                                 new_pack_size=i.pack_size)
                            changed.append(f"{i.name} {i.pack_price} → {ln.pack_price}")
                            i.pack_price = ln.pack_price
                            i.save(update_fields=["pack_price", "updated_at"])
                if g.order and g.order.status != PurchaseOrder.RECEIVED:
                    g.order.status = PurchaseOrder.RECEIVED
                    g.order.save(update_fields=["status"])
            log_change(request.user, "GRV", g.number, "saved", f"{n} lines" + (f"; prices: {'; '.join(changed)}" if changed else ""))
            msg = f"{g.number} saved – stock updated."
            if changed:
                msg += f" {len(changed)} ingredient price(s) updated."
            messages.success(request, msg)
            return redirect("stock:grv", pk=g.pk)
    else:
        initial_form = {}
        if g.pk:
            initial = [{"item": ln.ingredient.name, "packs_ordered": _num(ln.packs_ordered), "packs": _num(ln.packs),
                        "pack_price": _num(ln.pack_price)} for ln in g.lines.select_related("ingredient")]
        elif order:
            initial_form = {"supplier": order.supplier_id}
            initial = [{"item": ln.ingredient.name, "packs_ordered": _num(ln.packs), "packs": _num(ln.packs),
                        "pack_price": _num(ln.pack_price)} for ln in order.lines.select_related("ingredient")]
        else:
            initial = []
        form = GRVForm(instance=g, initial=initial_form)
        fs = GRVLineFormSet(prefix="ln", initial=initial)
    return render(request, "stock/grv_form.html", {"form": form, "fs": fs, "g": g, "order": order, "names": _item_names(),
                                                   "prices": _price_map()})


@need("stock")
def grv_detail(request, pk):
    g = get_object_or_404(GRV.objects.select_related("supplier", "order", "received_by"), pk=pk)
    from money.calc import grv_amount
    paid = sum((a.amount for a in g.allocations.all()), Z)
    amount = grv_amount(g)
    return render(request, "stock/grv_detail.html", {"g": g, "lines": g.lines.select_related("ingredient"),
                                                     "pay": {"amount": amount, "paid": paid, "owing": amount - paid,
                                                             "allocs": g.allocations.select_related("payment")}})


# ======================================================================= stock take
@need("stock")
def count_list(request):
    counts = list(StockCount.objects.select_related("created_by"))
    rows = []
    finals = [c for c in counts if c.status == StockCount.FINAL]
    for c in counts:
        prev = next((p for p in finals if p.date < c.date), None)
        cogs = None
        if c.status == StockCount.FINAL and prev and c.total_value is not None and prev.total_value is not None:
            purchases = purchases_between(prev.date, c.date)
            cogs = {"open": prev.total_value, "purch": purchases, "close": c.total_value,
                    "cos": prev.total_value + purchases - c.total_value}
        rows.append((c, cogs))
    from core.models import CompanySettings
    return render(request, "stock/count_list.html", {"rows": rows, "draft": next((c for c in counts if c.status == StockCount.DRAFT), None),
                                                     "cs": CompanySettings.get(), "manager": is_manager(request.user)})


@need("stock", EDIT)
@require_POST
def count_new(request):
    draft = StockCount.objects.filter(status=StockCount.DRAFT).first()
    if draft:
        messages.info(request, "Finish the stock take that is still busy first.")
        return redirect("stock:count_edit", pk=draft.pk)
    c = StockCount.objects.create(date=timezone.localdate(), created_by=request.user, as_at=timezone.now(),
                                  counted_by=request.user.first_name or request.user.username)
    log_change(request.user, "Stock take", c.number, "started")
    return redirect("stock:count_edit", pk=c.pk)


def _count_sections():
    ings = list(Ingredient.objects.filter(active=True).select_related("supplier", "recipe").order_by("supplier__name", "name"))
    bought = [i for i in ings if i.kind == Ingredient.BOUGHT]
    pack = [i for i in ings if i.kind == Ingredient.PACKAGING]
    prepared = [i for i in ings if i.kind == Ingredient.SUBRECIPE]
    products = list(Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__isnull=False).select_related("category")
                    .order_by("category__sort_order", "name"))
    return [("Ingredients (store)", "i", bought), ("Packaging", "i", pack), ("Prepared items (mother recipes)", "i", prepared),
            ("Shop floor products", "r", products)]


@need("stock", EDIT)
def count_edit(request, pk):
    c = get_object_or_404(StockCount, pk=pk)
    if c.status == StockCount.FINAL and not rights(request).owner:
        messages.error(request, "This stock take is final. Only the Manager can change it.")
        return redirect("stock:count", pk=pk)
    sections = _count_sections()
    existing = {("i", cl.ingredient_id) if cl.ingredient_id else ("r", cl.recipe_id): cl.qty for cl in c.lines.all()}
    reasons = {cl.ingredient_id: cl.reason for cl in c.lines.all() if cl.ingredient_id and cl.reason}
    only = None
    if request.GET.get("diff") == "1" and c.status == StockCount.DRAFT:
        vr, _ = variance_rows(c)
        only = {r["i"].pk for r in vr if r["counted"] is None or r["diff"]}
    if request.method == "POST":
        hf = CountHeaderForm(request.POST, instance=c)
        bad = []
        values = {}
        for _, kind, items in sections:
            for it in items:
                raw = request.POST.get(f"q_{kind}_{it.pk}", "").strip().replace(",", ".")
                if raw == "":
                    continue
                try:
                    v = Decimal(raw)
                    if v < 0:
                        raise InvalidOperation
                    values[(kind, it.pk)] = v
                except InvalidOperation:
                    bad.append(it.name)
        if hf.is_valid() and not bad:
            final = request.POST.get("final") == "1" and c.status == StockCount.FINAL and rights(request).owner
            calc = Calculator().preload()
            expected = ({cl.ingredient_id: cl.expected for cl in c.lines.all() if cl.ingredient_id}
                        if c.status == StockCount.FINAL else on_hand_all(c.as_at or c.created_at)[0])
            with transaction.atomic():
                hf.save()
                c.lines.all().delete()
                lines = []
                for _, kind, items in sections:
                    for it in items:
                        v = values.get((kind, it.pk))
                        if v is None:
                            if not final:
                                continue
                            v = Z  # not counted at final = none left
                        if kind == "i":
                            uc = calc.unit_cost(it) or Z
                            lines.append(CountLine(count=c, ingredient=it, qty=v, unit_cost=uc, reason=reasons.get(it.pk, ""),
                                                   expected=expected.get(it.pk) if it.kind != Ingredient.SUBRECIPE else None))
                        elif v:
                            lines.append(CountLine(count=c, recipe=it, qty=v, unit_cost=calc.cost_per_unit(it) or Z))
                CountLine.objects.bulk_create(lines)
                if c.status == StockCount.FINAL:
                    c.total_value = sum((ln.value for ln in lines), Z).quantize(Decimal("0.01"))
                    c.save()
            log_change(request.user, "Stock take", c.number, "corrected" if c.status == StockCount.FINAL else "saved")
            if request.POST.get("go") == "variance" or c.status == StockCount.FINAL:
                messages.success(request, "Counts saved.")
                return redirect("stock:count_variance", pk=c.pk)
            messages.success(request, "Counts saved. Carry on later, or look at the variance report.")
            return redirect(request.get_full_path())
        if bad:
            messages.error(request, "These counts are not numbers: " + ", ".join(bad[:10]))
    else:
        hf = CountHeaderForm(instance=c)
    rows = [(title, kind, [(it, existing.get((kind, it.pk))) for it in items if only is None or (kind == "i" and it.pk in only)])
            for title, kind, items in sections]
    rows = [r for r in rows if r[2]]
    return render(request, "stock/count_form.html", {"c": c, "hf": hf, "sections": rows, "only": only is not None})


@need("stock")
def count_detail(request, pk):
    c = get_object_or_404(StockCount, pk=pk)
    lines = list(c.lines.select_related("ingredient", "ingredient__supplier", "recipe"))
    groups = {"bought": Z, "packaging": Z, "subrecipe": Z, "product": Z}
    diffs = []
    for ln in lines:
        key = ln.ingredient.kind if ln.ingredient_id else "product"
        groups[key] += ln.value
        if ln.expected is not None and ln.qty != ln.expected:
            diffs.append(ln)
    diffs.sort(key=lambda ln: -abs((ln.qty - ln.expected) * ln.unit_cost))
    return render(request, "stock/count_detail.html", {"c": c, "lines": lines, "groups": groups, "diffs": diffs[:25],
                                                       "total": sum(groups.values(), Z)})


@need("stock")
def count_sheet(request, pk):
    c = get_object_or_404(StockCount, pk=pk)
    return render(request, "stock/print_count.html", {"c": c, "sections": _count_sections()})


# ======================================================================= stock take: variance, recount, finalise
def is_manager(user):
    """Only the managers may finalise a stock take: the Manager (owner login) and the Assistant Manager."""
    if user.is_superuser:
        return True
    acc = getattr(user, "access", None)
    return bool(acc and acc.role in ("assistant_manager", "manager"))


def _limit():
    from core.models import CompanySettings
    return CompanySettings.get().stock_variance_limit or Decimal("100")


def variance_rows(c):
    """Every store ingredient / packaging item: expected, counted, difference and its value."""
    calc = Calculator().preload()
    lines = {cl.ingredient_id: cl for cl in c.lines.filter(ingredient__isnull=False).select_related("ingredient")}
    if c.status == StockCount.FINAL:
        expected = {k: cl.expected for k, cl in lines.items()}
    else:
        expected, _ = on_hand_all(c.as_at or c.created_at)
    limit = _limit()
    rows = []
    items = Ingredient.objects.filter(active=True).exclude(kind=Ingredient.SUBRECIPE).select_related("supplier")
    seen = set()
    for i in list(items) + [cl.ingredient for cl in lines.values() if not cl.ingredient.active]:
        if i.pk in seen:
            continue
        seen.add(i.pk)
        cl = lines.get(i.pk)
        exp = expected.get(i.pk)
        exp = Z if exp is None else exp
        uc = (cl.unit_cost if (cl and c.status == StockCount.FINAL) else (calc.unit_cost(i) or Z))
        counted = cl.qty if cl else None
        if counted is None and not exp:
            continue            # nothing expected, nothing counted
        diff = (counted if counted is not None else Z) - exp
        val = (diff * uc).quantize(Decimal("0.01"))
        rows.append({"i": i, "exp": exp, "counted": counted, "diff": diff, "value": val, "uc": uc,
                     "reason": cl.reason if cl else "", "big": abs(val) >= limit, "line": cl})
    rows.sort(key=lambda r: (r["counted"] is not None, -abs(r["value"])))
    return rows, limit


@need("stock")
def count_variance(request, pk):
    c = get_object_or_404(StockCount, pk=pk)
    rows, limit = variance_rows(c)
    draft = c.status == StockCount.DRAFT
    manager = is_manager(request.user)
    if request.method == "POST" and draft:
        if not rights(request).has("stock", EDIT):
            return redirect("stock:count_variance", pk=pk)
        for r in rows:
            if r["line"] is not None and f"r_{r['i'].pk}" in request.POST:
                r["line"].reason = request.POST.get(f"r_{r['i'].pk}", "").strip()[:500]
                r["line"].save(update_fields=["reason"])
                r["reason"] = r["line"].reason
        if request.POST.get("finalise") == "1":
            missing = [r["i"].name for r in rows if r["counted"] is None]
            no_reason = [r["i"].name for r in rows if r["big"] and r["counted"] is not None and not r["reason"]]
            if not manager:
                messages.error(request, "Only a manager can finalise the stock take.")
            elif missing:
                messages.error(request, f"{len(missing)} item(s) are not counted yet – count them (type 0 if there are none): "
                               + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
            elif no_reason:
                messages.error(request, f"Explain every difference of ${limit:,.0f} or more before finalising: " + ", ".join(no_reason[:8]))
            else:
                _finalise(c, request.user)
                log_change(request.user, "Stock take", c.number, "finalised",
                           f"net difference ${sum((r['value'] for r in rows), Z):,.2f}")
                messages.success(request, "Stock take finalised – stock levels now start from these counts.")
                return redirect("stock:count_variance", pk=pk)
        else:
            messages.success(request, "Reasons saved.")
        return redirect("stock:count_variance", pk=pk)
    short = sum((r["value"] for r in rows if r["value"] < 0), Z)
    over = sum((r["value"] for r in rows if r["value"] > 0), Z)
    return render(request, "stock/count_variance.html", {
        "c": c, "rows": rows, "limit": limit, "draft": draft, "manager": manager,
        "short": short, "over": over, "net": short + over,
        "n_missing": sum(1 for r in rows if r["counted"] is None),
        "n_diff": sum(1 for r in rows if r["counted"] is not None and r["diff"]),
        "n_reason": sum(1 for r in rows if r["big"] and r["counted"] is not None and not r["reason"]),
        "mode": usage_mode()})


def _finalise(c, user):
    calc = Calculator().preload()
    with transaction.atomic():
        sections = _count_sections()
        have = {("i", cl.ingredient_id) if cl.ingredient_id else ("r", cl.recipe_id) for cl in c.lines.all()}
        extra = []
        for _, kind, items in sections:
            for it in items:
                if kind == "i" and ("i", it.pk) not in have:
                    extra.append(CountLine(count=c, ingredient=it, qty=Z, unit_cost=calc.unit_cost(it) or Z,
                                           expected=None))
        CountLine.objects.bulk_create(extra)
        c.status = StockCount.FINAL
        c.finalized_at = timezone.now()
        c.finalized_by = user
        c.total_value = sum((ln.value for ln in c.lines.all()), Z).quantize(Decimal("0.01"))
        c.save()


@need("stock")
@require_POST
def count_settings(request):
    from core.models import CompanySettings
    if not is_manager(request.user):
        messages.error(request, "Only a manager can change this.")
        return redirect("stock:counts")
    cs = CompanySettings.get()
    mode = request.POST.get("stock_usage")
    if mode in ("sales", "production"):
        cs.stock_usage = mode
    try:
        lim = Decimal(request.POST.get("limit", "").replace(",", "") or "100")
        if lim >= 0:
            cs.stock_variance_limit = lim
    except InvalidOperation:
        pass
    cs.save()
    log_change(request.user, "Settings", "Stock usage", "changed", f"{cs.stock_usage}, explain from ${cs.stock_variance_limit}")
    messages.success(request, "Saved.")
    return redirect("stock:counts")
