import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.access import EDIT, VIEW, need, rights
from core.models import log_change
from core.templatetags.pondo import money

from .calc import Calculator, CycleError
from .forms import IngredientForm, LineFormSet, NameForm, RecipeForm
from .models import Category, Ingredient, IngredientPriceChange, Recipe, RecipeLine, Supplier


# ----------------------------------------------------------------- recipes
def method_lines(r):
    """Method steps, one per line, without the typed '1.' numbers (the page numbers them)."""
    return [re.sub(r"^\s*\d+\s*[.)\-:]\s*", "", x).strip() for x in r.method.splitlines() if x.strip()]


@need("recipes")
def recipe_list(request):
    """Recipes & Prices: every recipe in number order with its costs, selling price (typed straight in) and GP.
    Free recipe numbers stay in the list as empty lines."""
    from .numbers import free_runs, stats

    can = rights(request)
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("cat", "")
    show = request.GET.get("show", "all")

    def pct(name):  # GP range, typed as a % ("49.99")
        raw = request.GET.get(name, "").strip().replace("%", "").replace(",", ".")
        try:
            return Decimal(raw) if raw else None
        except InvalidOperation:
            return None
    gp_min, gp_max = pct("gp_min"), pct("gp_max")
    gp_range = (gp_min is not None or gp_max is not None) and can.costs
    if request.method == "POST":
        if not can.has("prices", EDIT):
            messages.error(request, "You can look at prices but not change them.")
            return redirect(request.get_full_path())
        changed = []
        ids = [int(k[1:]) for k in request.POST if k.startswith("p") and k[1:].isdigit()]
        for r in Recipe.objects.filter(pk__in=ids, is_subrecipe=False):
            raw = request.POST[f"p{r.pk}"].strip().replace("$", "").replace(",", ".")
            try:
                new = Decimal(raw).quantize(Decimal("0.01")) if raw else None
            except InvalidOperation:
                messages.error(request, f"'{raw}' is not a price ({r.name}). Nothing saved for that line.")
                continue
            if new != r.sell_price:
                log_change(request.user, "Prices", r.name, "price changed", f"{r.sell_price} → {new}")
                r.sell_price = new
                r.save(update_fields=["sell_price", "updated_at"])
                changed.append(r)
        if len(changed) == 1:
            messages.success(request, f"Saved {changed[0].name} – {money(changed[0].sell_price)}.")
        else:
            messages.success(request, f"{len(changed)} prices saved." if changed else "No prices were changed.")
        back = {"q": q, "cat": cat, "show": show if show != "all" else "", "saved": ",".join(str(r.pk) for r in changed),
                "at": request.POST.get("at", ""), "gp_min": request.GET.get("gp_min", ""), "gp_max": request.GET.get("gp_max", "")}
        return redirect(f"{reverse('costing:recipes')}?{urlencode({k: v for k, v in back.items() if v})}")

    qs = Recipe.objects.filter(active=True).select_related("category")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(number__icontains=q) | Q(lines__ingredient__name__icontains=q)).distinct()
    if cat:
        qs = qs.filter(category_id=cat)
    if show == "products":
        qs = qs.filter(is_subrecipe=False)
    elif show == "mother":
        qs = qs.filter(is_subrecipe=True)
    elif show in ("low", "noprice"):
        qs = qs.filter(is_subrecipe=False)
    if gp_range:  # GP only exists for products with a selling price
        qs = qs.filter(is_subrecipe=False, sell_price__isnull=False)
    elif show == "archived":
        qs = Recipe.objects.filter(active=False).select_related("category")
    saved = {int(x) for x in request.GET.get("saved", "").split(",") if x.isdigit()}
    calc = Calculator().preload()
    rows = []
    for r in qs.order_by("number"):  # always in recipe-number order
        try:
            sm = calc.summary(r)
        except CycleError:
            sm = None
        if r.pk not in saved:  # a line just changed stays, even when it no longer fits the filter
            if show == "low" and not (sm and sm["gp"] is not None and sm["gp"] < calc.settings.target_gp):
                continue
            if show == "noprice" and r.sell_price is not None:
                continue
            if gp_range:
                g = sm["gp"] * 100 if sm and sm["gp"] is not None else None
                if g is None or (gp_min is not None and g < gp_min) or (gp_max is not None and g > gp_max):
                    continue
        r.just_saved = r.pk in saved
        rows.append((r, sm))
    # the full list keeps every free number in its place, as an empty line
    gaps = show == "all" and not q and not cat and not gp_range
    free = set()
    if gaps:
        for a, b in free_runs():
            free.update(range(a, b + 1))
    items = []
    pending = sorted(free)
    for r, sm in rows:
        while pending and pending[0] < r.number:
            items.append({"free": True, "number": pending.pop(0)})
        items.append({"free": False, "r": r, "s": sm})
    gps = [sm["gp"] for r, sm in rows if sm and not r.is_subrecipe and sm["gp"] is not None]
    cats = Category.objects.annotate(n=Count("recipes", filter=Q(recipes__active=True))).filter(n__gt=0)
    return render(request, "costing/recipe_list.html", {
        "items": items, "rows": rows, "q": q, "cat": cat, "show": show, "cats": cats,
        "total": Recipe.objects.filter(active=True).count(), "numbers": stats(), "gaps": gaps,
        "avg": sum(gps) / len(gps) if gps else None, "editing": can.prices_edit and show != "archived",
        "at": request.GET.get("at", ""), "gp_range": gp_range,
        "gp_min": request.GET.get("gp_min", ""), "gp_max": request.GET.get("gp_max", ""), "found": len(rows)})


def _lines_by_section(calc, r):
    sections = []
    total = calc.batch_cost(r) or Decimal("0")
    for key, label in RecipeLine.SECTION_CHOICES:
        items = []
        for ln in calc.lines(r):
            if ln.section != key:
                continue
            cost = calc.line_cost(r, ln)
            items.append({
                "ln": ln, "qty": calc.line_qty(r, ln), "unit_cost": calc.unit_cost(ln.ingredient), "cost": cost,
                "share": (cost / total) if (cost is not None and total) else None,
            })
        if items:
            sub = sum((i["cost"] or 0) for i in items)
            sections.append({"key": key, "label": label, "items": items, "subtotal": sub})
    return sections


@need("recipes")
def recipe_detail(request, pk):
    r = get_object_or_404(Recipe.objects.select_related("category"), pk=pk)
    calc = Calculator()
    try:
        s = calc.summary(r)
        sections = _lines_by_section(calc, r)
        error = None
    except CycleError as e:
        s, sections, error = None, [], str(e)
    used_in = []
    ing = getattr(r, "as_ingredient", None)
    if ing:
        used_in = Recipe.objects.filter(lines__ingredient=ing).distinct()
    missing = [ln.ingredient for ln in calc.lines(r) if calc.unit_cost(ln.ingredient) is None]
    return render(request, "costing/recipe_detail.html",
                  {"r": r, "s": s, "sections": sections, "error": error, "used_in": used_in, "as_ing": ing,
                   "missing": missing, "method_lines": method_lines(r)})


PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@need("recipes", EDIT)
@require_POST
def recipe_photo(request, pk):
    """Add, change or remove the product photo from the recipe page."""
    import os

    from django.utils.text import slugify

    r = get_object_or_404(Recipe, pk=pk)
    old = r.photo.name if r.photo else ""
    if request.POST.get("remove"):
        r.photo = ""
        r.save(update_fields=["photo", "updated_at"])
        msg = "Photo removed."
    else:
        f = request.FILES.get("photo")
        ext = os.path.splitext(f.name)[1].lower() if f else ""
        if not f:
            messages.error(request, "Choose a photo first.")
            return redirect("costing:recipe", pk=pk)
        if ext not in PHOTO_TYPES:
            messages.error(request, "That is not a photo. Use a JPG or PNG picture.")
            return redirect("costing:recipe", pk=pk)
        if f.size > 15 * 1024 * 1024:
            messages.error(request, "That photo is too big (over 15 MB).")
            return redirect("costing:recipe", pk=pk)
        r.photo.save(f"{r.number}-{slugify(r.name)[:40] or 'product'}{ext}", f, save=False)
        r.save(update_fields=["photo", "updated_at"])
        msg = "Photo saved."
    if old and old != r.photo.name:
        try:
            r.photo.storage.delete(old)
        except OSError:
            pass
    log_change(request.user, "Recipes", r.name, "photo " + ("removed" if request.POST.get("remove") else "changed"))
    messages.success(request, msg)
    return redirect("costing:recipe", pk=pk)


def _save_lines(recipe, formset):
    RecipeLine.objects.filter(recipe=recipe).delete()
    pos = 0
    for f in formset.forms:
        cd = f.cleaned_data
        if not cd or cd.get("DELETE") or cd.get("empty"):
            continue
        pos += 1
        RecipeLine.objects.create(recipe=recipe, section=cd["section"], ingredient=cd["ingredient_obj"],
                                  qty=cd["qty"], qty_mode=cd["qty_mode"], position=pos)


def _sync_subrecipe_ingredient(r):
    """A mother recipe automatically appears on the ingredient list (priced from the recipe)."""
    ing = Ingredient.objects.filter(recipe=r).first()
    if r.is_subrecipe:
        if ing is None:
            ing = Ingredient.objects.filter(name__iexact=r.name, kind=Ingredient.SUBRECIPE, recipe__isnull=True).first()
        if ing is None:
            name = r.name
            if Ingredient.objects.filter(name__iexact=name).exists():
                name = f"{r.name} (recipe)"
            ing = Ingredient(name=name, kind=Ingredient.SUBRECIPE, unit="kg")
        ing.recipe = r
        ing.kind = Ingredient.SUBRECIPE
        ing.active = r.active
        ing.save()


@need("recipes", EDIT)
def recipe_edit(request, pk=None):
    r = get_object_or_404(Recipe, pk=pk) if pk else Recipe()
    copy_from = None
    if not pk and request.GET.get("copy"):
        copy_from = get_object_or_404(Recipe, pk=request.GET["copy"])
    if request.method == "POST":
        old_price = r.sell_price
        form = RecipeForm(request.POST, request.FILES, instance=r)
        _limit_form(request, form)
        fs = LineFormSet(request.POST, prefix="ln")
        fs.recipe = r if r.pk else None
        if form.is_valid() and fs.is_valid():
            with transaction.atomic():
                rec = form.save()
                _save_lines(rec, fs)
                _sync_subrecipe_ingredient(rec)
                try:
                    Calculator().batch_cost(rec)
                except CycleError as e:
                    transaction.set_rollback(True)
                    messages.error(request, str(e))
                    return render(request, "costing/recipe_form.html", _form_ctx(form, fs, r))
            log_change(request.user, "Recipes", rec.name, "changed" if pk else "added")
            if pk and rec.sell_price != old_price:
                log_change(request.user, "Prices", rec.name, "price changed", f"{old_price} → {rec.sell_price}")
            messages.success(request, f"Saved {rec.name}." + (f" New price {money(rec.sell_price)}."
                                                               if pk and rec.sell_price != old_price and rec.sell_price else ""))
            return redirect("costing:recipe", pk=rec.pk)
    else:
        src = copy_from or r
        initial_lines = [{"section": ln.section, "ingredient": ln.ingredient.name, "qty": format(ln.qty.normalize(), "f"),
                          "qty_mode": ln.qty_mode} for ln in src.lines.select_related("ingredient")] if src.pk else []
        if copy_from:
            form = RecipeForm(instance=Recipe(), initial={
                "name": f"{copy_from.name} (copy)", "category": copy_from.category_id,
                "is_subrecipe": copy_from.is_subrecipe, "scaling_weight": copy_from.scaling_weight,
                "loss_percent": copy_from.weight_loss * 100 or None, "bake_temp": copy_from.bake_temp,
                "bake_time": copy_from.bake_time, "method": copy_from.method, "allergens": copy_from.allergens,
                "sell_price": copy_from.sell_price, "sold_per": copy_from.sold_per, "active": True})
            _limit_form(request, form)
        else:
            form = RecipeForm(instance=r)
            want = request.GET.get("number", "")
            if not pk and want.isdigit():  # "+ New recipe with this number" from the list
                form.initial["number"] = int(want)
        _limit_form(request, form)
        fs = LineFormSet(prefix="ln", initial=initial_lines)
    return render(request, "costing/recipe_form.html", _form_ctx(form, fs, r))


def _limit_form(request, form):
    if not rights(request).has("prices", EDIT):
        form.fields.pop("sell_price", None)
        form.fields.pop("vat_percent", None)
        form.fields.pop("sold_per", None)
    return form


def _form_ctx(form, fs, r):
    calc = Calculator().preload()
    ings = list(Ingredient.objects.filter(active=True).select_related("recipe"))
    costs = {}
    for i in ings:
        try:
            c = calc.unit_cost(i)
        except CycleError:
            c = None
        costs[i.name] = {"unit": i.unit, "cost": float(c) if c is not None else None}
    from .numbers import suggestions

    return {"form": form, "fs": fs, "r": r, "ingredient_names": [(i.name, i.unit) for i in ings], "ing_costs": costs,
            "free_numbers": [] if r.pk else suggestions()}


@need("recipes", EDIT)
@require_POST
def recipe_archive(request, pk):
    r = get_object_or_404(Recipe, pk=pk)
    r.active = not r.active
    r.save()
    _sync_subrecipe_ingredient(r)
    log_change(request.user, "Recipes", r.name, "restored" if r.active else "archived")
    messages.success(request, f"{r.name} {'is back in the list' if r.active else 'was archived (hidden). You can restore it from Archived.'}")
    return redirect("costing:recipe", pk=r.pk)


@need("recipes")
def recipe_print(request, pk, kind):
    if kind not in ("card", "costing") or (kind == "costing" and not rights(request).costs):
        return redirect("costing:recipe", pk=pk)
    r = get_object_or_404(Recipe.objects.select_related("category"), pk=pk)
    calc = Calculator()
    scale = request.GET.get("make")
    ctx = {"r": r, "s": calc.summary(r), "sections": _lines_by_section(calc, r), "kind": kind,
           "method_lines": method_lines(r), "art": card_art(r)}
    # Scaled batch for the production card ("make 60 loaves")
    try:
        make = Decimal(scale) if scale else None
    except InvalidOperation:
        make = None
    if make and ctx["s"]["yield"]:
        f = make / ctx["s"]["yield"]
        for sec in ctx["sections"]:
            for it in sec["items"]:
                it["qty"] = it["qty"] * f
        ctx["make"] = make
    return render(request, f"costing/print_{kind}.html", ctx)


# ----------------------------------------------------------------- ingredients
@need("ingredients")
def ingredient_list(request):
    q = request.GET.get("q", "").strip()
    sup = request.GET.get("sup", "")
    kind = request.GET.get("kind", "")
    qs = Ingredient.objects.filter(active=True).select_related("supplier", "recipe").annotate(
        n_used=Count("used_in__recipe", filter=Q(used_in__recipe__active=True), distinct=True))
    if request.GET.get("show") == "archived":
        qs = Ingredient.objects.filter(active=False).select_related("supplier", "recipe").annotate(n_used=Count("used_in"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    if sup:
        qs = qs.filter(supplier_id=sup)
    if kind:
        qs = qs.filter(kind=kind)
    calc = Calculator().preload()
    rows = [(i, calc.unit_cost(i)) for i in qs]
    return render(request, "costing/ingredient_list.html",
                  {"rows": rows, "q": q, "sup": sup, "kind": kind, "suppliers": Supplier.objects.filter(active=True),
                   "kinds": Ingredient.KIND_CHOICES})


@need("ingredients")
def ingredient_detail(request, pk):
    i = get_object_or_404(Ingredient.objects.select_related("supplier", "recipe"), pk=pk)
    calc = Calculator()
    uses = []
    for ln in RecipeLine.objects.filter(ingredient=i).select_related("recipe", "recipe__category"):
        r = ln.recipe
        uses.append({"r": r, "qty": calc.line_qty(r, ln), "cost": calc.line_cost(r, ln), "section": ln.get_section_display()})
    return render(request, "costing/ingredient_detail.html",
                  {"i": i, "unit_cost": calc.unit_cost(i), "uses": uses,
                   "history": i.price_changes.select_related("user")[:20]})


@need("ingredients", EDIT)
def ingredient_edit(request, pk=None):
    i = get_object_or_404(Ingredient, pk=pk) if pk else Ingredient()
    old_price, old_size = i.pack_price, i.pack_size
    form = IngredientForm(request.POST or None, instance=i)
    if request.method == "POST" and form.is_valid():
        ing = form.save()
        if pk and (old_price != ing.pack_price or old_size != ing.pack_size):
            IngredientPriceChange.objects.create(ingredient=ing, user=request.user, old_price=old_price,
                                                 new_price=ing.pack_price, old_pack_size=old_size,
                                                 new_pack_size=ing.pack_size)
        log_change(request.user, "Ingredients", ing.name, "changed" if pk else "added",
                   f"price {old_price} → {ing.pack_price}" if pk and old_price != ing.pack_price else "")
        messages.success(request, f"Saved {ing.name}.")
        return redirect(request.GET.get("next") or reverse("costing:ingredient", args=[ing.pk]))
    return render(request, "costing/ingredient_form.html", {"form": form, "i": i})


# ----------------------------------------------------------------- products & prices
@need("prices")
def price_list(request):
    """The plain price list – only for people who may see prices but not recipes (e.g. a cashier).
    Everybody else uses Recipes & Prices, which has everything on one page."""
    cat = request.GET.get("cat", "")
    flt = request.GET.get("f", "")
    if rights(request).recipes_view and request.method == "GET":
        back = {"cat": cat, "show": {"low": "low", "noprice": "noprice"}.get(flt, "products" if not cat else ""),
                "q": request.GET.get("q", ""), "saved": request.GET.get("saved", ""), "at": request.GET.get("at", "")}
        return redirect(f"{reverse('costing:recipes')}?{urlencode({k: v for k, v in back.items() if v})}")
    qs = Recipe.objects.filter(active=True, is_subrecipe=False).select_related("category")
    if cat:
        qs = qs.filter(category_id=cat)
    calc = Calculator().preload()
    if request.method == "POST":
        if not rights(request).has("prices", EDIT):
            messages.error(request, "You can look at prices but not change them.")
            return redirect(request.get_full_path())
        changed = []
        for r in qs:
            key = f"p{r.pk}"
            if key not in request.POST:
                continue
            raw = request.POST[key].strip().replace("$", "").replace(",", ".")
            try:
                new = Decimal(raw).quantize(Decimal("0.01")) if raw else None
            except InvalidOperation:
                messages.error(request, f"'{raw}' is not a price ({r.name}). Nothing saved for that line.")
                continue
            if new != r.sell_price:
                log_change(request.user, "Prices", r.name, "price changed", f"{r.sell_price} → {new}")
                r.sell_price = new
                r.save(update_fields=["sell_price", "updated_at"])
                changed.append(r)
        if len(changed) == 1:
            messages.success(request, f"Saved {changed[0].name} – {money(changed[0].sell_price)}.")
        else:
            messages.success(request, f"{len(changed)} prices saved." if changed else "No prices were changed.")
        # come back to the same place: the same search, and the lines just changed stay on the list
        back = {"cat": cat, "f": flt, "edit": "1", "q": request.POST.get("q", "").strip()[:60],
                "saved": ",".join(str(r.pk) for r in changed), "at": request.POST.get("at", "")}
        return redirect(f"{reverse('costing:prices')}?{urlencode({k: v for k, v in back.items() if v})}")
    saved = {int(x) for x in request.GET.get("saved", "").split(",") if x.isdigit()}
    rows = []
    for r in qs:
        s = calc.summary(r)
        if r.pk not in saved:  # a line just changed stays, even when it no longer fits the filter
            if flt == "low" and not (s["gp"] is not None and s["gp"] < calc.settings.target_gp):
                continue
            if flt == "noprice" and r.sell_price is not None:
                continue
        r.just_saved = r.pk in saved
        rows.append((r, s))
    gps = [s["gp"] for _, s in rows if s["gp"] is not None]
    avg = sum(gps) / len(gps) if gps else None
    return render(request, "costing/price_list.html",
                  {"rows": rows, "cat": cat, "f": flt, "cats": Category.objects.all(), "avg": avg,
                   "editing": rights(request).prices_edit,  # prices are always typed straight into the list
 "q": request.GET.get("q", ""),
                   "at": request.GET.get("at", "")})


# ----------------------------------------------------------------- lists (categories, suppliers)
@need(owner=True)
def lists_view(request):
    if request.method == "POST":
        which = request.POST.get("which")
        model = {"cat": Category, "sup": Supplier}.get(which)
        form = NameForm(request.POST)
        if model and form.is_valid():
            name = " ".join(form.cleaned_data["name"].split())
            pk = request.POST.get("pk")
            if model.objects.filter(name__iexact=name).exclude(pk=pk or 0).exists():
                messages.error(request, f"'{name}' is already on the list.")
            elif pk:
                obj = get_object_or_404(model, pk=pk)
                old = obj.name
                obj.name = name
                obj.save()
                log_change(request.user, "Lists", name, "renamed", f"was {old}")
                messages.success(request, f"Renamed to {name}.")
            else:
                model.objects.create(name=name)
                log_change(request.user, "Lists", name, "added")
                messages.success(request, f"Added {name}.")
        return redirect("costing:lists")
    return render(request, "costing/lists.html", {
        "cats": Category.objects.annotate(n=Count("recipes")),
        "sups": Supplier.objects.annotate(n=Count("ingredients")),
    })


# ----------------------------------------------------------------- price cards & posters (brand styles)
CARD_STYLES = {
    "orange": {"label": "Pondo Orange", "bg": "#e56026", "ink": "#fff3d7", "logo": "primary_reverse_cream",
               "burst": "teal", "pattern": "cream", "op": ".12", "badge": "badge_burgundy_on_cream",
               "win": "#fff3d7", "win2": "#ffe6bf", "wart": "orange", "chip": "#7a1315"},
    "burgundy": {"label": "Pondo Burgundy", "bg": "#7a1315", "ink": "#fff3d7", "logo": "primary_reverse_cream",
                 "burst": "orange", "pattern": "warm", "op": ".12", "badge": "badge_burgundy_on_cream",
                 "win": "#f89b47", "win2": "#fbb46f", "wart": "burgundy", "chip": "#e56026"},
    "teal": {"label": "Pondo Teal", "bg": "#218d80", "ink": "#fff3d7", "logo": "primary_reverse_cream",
             "burst": "orange", "pattern": "cream", "op": ".11", "badge": "badge_burgundy_on_cream",
             "win": "#fff3d7", "win2": "#ffe6bf", "wart": "teal", "chip": "#7a1315"},
    "warm": {"label": "Warm Orange", "bg": "#f89b47", "ink": "#7a1315", "logo": "primary_burgundy",
             "burst": "burgundy", "pattern": "burgundy", "op": ".09", "badge": "badge_burgundy_on_cream",
             "win": "#fff3d7", "win2": "#ffe6bf", "wart": "burgundy", "chip": "#7a1315"},
    "cream": {"label": "Bakery Cream", "bg": "#fff3d7", "ink": "#7a1315", "logo": "primary_orange",
              "burst": "burgundy", "pattern": "orange", "op": ".1", "badge": "badge_cream_on_orange",
              "win": "#218d80", "win2": "#2e9c8e", "wart": "cream", "chip": "#e56026"},
}
CARD_MIX = ["orange", "cream", "burgundy", "teal", "warm"]
CARD_ART = [("donut", ("doughnut", "donut")), ("cupcake", ("cupcake", "muffin")), ("pie", ("pie", "tart", "quiche")),
            ("cookie", ("cookie", "biscuit", "rusk")), ("samoosa", ("samoosa", "samosa", "savour", "kiosk")),
            ("bread", ("bread", "loaf", "roll", "bun")), ("glazed_bun", ("cake", "square", "slice", "dessert", "seasonal")),
            ("bun", ("pastr", "danish", "croissant", "morning"))]


def card_art(r):
    """A brand illustration that fits the product (used when there is no photo)."""
    text = f"{r.name} {r.category.name if r.category else ''}".lower()
    for art, words in CARD_ART:
        if any(w in text for w in words):
            return art
    return None
CARD_LAYOUTS = {
    "shelf": ("Shelf cards", "8 per A4 page – for the counter and shelves"),
    "big": ("Big cards", "4 per A4 page – for the display fridge and trays"),
    "poster": ("Posters", "1 per A4 page – “Today's special”, with the photo"),
    "menu": ("Price list / menu", "All the chosen products on one A4 page, by category"),
}


@need("prices")
def price_cards(request):
    """Pick products, a layout and a brand colour style; the print opens in a new tab."""
    qs = (Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__isnull=False)
          .select_related("category").order_by("category__sort_order", "category__name", "name"))
    cats = Category.objects.all()
    return render(request, "costing/price_cards.html", {"products": qs, "cats": cats, "styles": CARD_STYLES,
                                                        "layouts": CARD_LAYOUTS})


@need("prices")
def price_cards_print(request):
    ids = [int(x) for x in request.GET.getlist("p") if x.isdigit()]
    layout = request.GET.get("layout", "shelf")
    if layout not in CARD_LAYOUTS:
        layout = "shelf"
    style = request.GET.get("style", "mix")
    photos = request.GET.get("photos") == "1"
    only = request.GET.get("only", "1") == "1"
    head = (request.GET.get("head") or "Today's special").strip()[:40]
    sub = (request.GET.get("sub") or "").strip()[:60]
    items = list(Recipe.objects.filter(pk__in=ids, sell_price__isnull=False).select_related("category")
                 .order_by("category__sort_order", "category__name", "name"))
    cards = []
    for n, r in enumerate(items):
        key = CARD_MIX[n % len(CARD_MIX)] if style not in CARD_STYLES else style
        nm = r.name.strip()
        size = "xl" if len(nm) <= 10 else "l" if len(nm) <= 16 else "m" if len(nm) <= 26 else "s"
        cards.append({"r": r, "s": CARD_STYLES[key], "key": key, "size": size, "art": card_art(r),
                      "art_col": "cream" if CARD_STYLES[key]["ink"] == "#fff3d7" else "burgundy"})
    per = {"shelf": 8, "big": 4, "poster": 1, "menu": 10 ** 6}[layout]
    pages = [cards[i:i + per] for i in range(0, len(cards), per)] or [[]]
    menu = []
    if layout == "menu":
        groups = []
        for c in cards:
            cat = c["r"].category.name if c["r"].category else "Other"
            if not groups or groups[-1][0] != cat:
                groups.append((cat, []))
            groups[-1][1].append(c["r"])
        # fill A4 pages: two columns of about 30 lines; a category heading takes 2 lines
        room, page, left = 46, [], 46
        for cat, items in groups:
            first = True
            while items:
                if left < 4:
                    menu.append(page); page, left = [], room
                take = items[:left - 2]
                page.append((cat if first else f"{cat} (continued)", take))
                left -= len(take) + 2
                items = items[len(take):]
                first = False
        if page:
            menu.append(page)
    menu_style = CARD_STYLES.get(style, CARD_STYLES["cream"])
    return render(request, "costing/price_cards_print.html", {
        "pages": pages, "layout": layout, "photos": photos, "only": only, "head": head, "sub": sub,
        "menu": menu, "ms": menu_style, "n": len(cards),
    })
