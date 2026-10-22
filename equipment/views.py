import datetime
import re
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.access import EDIT, need
from core.models import log_change

from .calc import count_summary, year_schedule
from .forms import CategoryFormSet, ItemForm, LocationFormSet
from .models import CountLine, EquipmentCategory, EquipmentCount, Item, Location

Z = Decimal("0")


def _month(request):
    today = timezone.localdate()
    try:
        return datetime.date.fromisoformat(request.GET.get("month", "") + "-01")
    except ValueError:
        return today.replace(day=1)


def _next_asset_no():
    nums = [int(m.group(1)) for a in Item.objects.values_list("asset_no", flat=True) if (m := re.match(r"EQ-(\d+)$", a))]
    return f"EQ-{(max(nums) + 1) if nums else 1:03d}"


@need("equipment")
def register(request):
    month = timezone.localdate().replace(day=1)
    cat, loc, q = request.GET.get("cat", ""), request.GET.get("loc", ""), request.GET.get("q", "").strip()
    show = request.GET.get("show", "")
    qs = Item.objects.select_related("category", "location")
    if cat:
        qs = qs.filter(category_id=cat)
    if loc:
        qs = qs.filter(location_id=loc) if loc != "none" else qs.filter(location__isnull=True)
    if q:
        qs = qs.filter(Q(description__icontains=q) | Q(asset_no__icontains=q) | Q(serial__icontains=q) | Q(supplier__icontains=q))
    if show != "all":
        qs = qs.filter(disposed_on__isnull=True)
    items = list(qs)
    rows = [(i, i.book_value(month), i.dep_in(month)) for i in items]
    return render(request, "equipment/register.html", {
        "rows": rows, "cat": cat, "loc": loc, "q": q, "show": show, "month": month,
        "cats": EquipmentCategory.objects.all(), "locs": Location.objects.all(),
        "cost": sum((i.total_cost for i in items), Z), "book": sum((b for _, b, _ in rows), Z),
        "dep": sum((d for _, _, d in rows), Z), "pieces": sum(i.qty for i in items),
        "no_loc": Item.objects.filter(location__isnull=True, disposed_on__isnull=True).count()})


@need("equipment", EDIT)
def item_edit(request, pk=None):
    item = get_object_or_404(Item, pk=pk) if pk else Item(asset_no=_next_asset_no())
    form = ItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        log_change(request.user, "Equipment", str(item), "changed" if pk else "added")
        messages.success(request, f"Saved {item.asset_no}.")
        return redirect("equipment:register")
    month = timezone.localdate().replace(day=1)
    history = list(item.counts.select_related("count").order_by("-count__month")[:12]) if item.pk else []
    return render(request, "equipment/item_form.html", {"form": form, "item": item, "month": month, "history": history,
                                                        "book": item.book_value(month) if item.pk else None,
                                                        "dep_to": item.dep_to(month) if item.pk else None})


@need("equipment")
def count_view(request):
    month = _month(request)
    c = EquipmentCount.objects.filter(month=month).first()
    items = [i for i in Item.objects.select_related("category", "location").order_by("location__sort_order", "location__name", "asset_no")
             if i.expected_qty(month) > 0]
    if request.method == "POST":
        from core.access import rights
        if not rights(request).has("stock", EDIT):
            return redirect("equipment:count")
        with transaction.atomic():
            c = c or EquipmentCount(month=month, created_by=request.user)
            c.counted_by = request.POST.get("counted_by", "")[:80]
            try:
                c.date = datetime.date.fromisoformat(request.POST.get("date", ""))
            except ValueError:
                c.date = timezone.localdate()
            c.notes = request.POST.get("notes", "")[:2000]
            c.save()
            n = 0
            for i in items:
                raw = request.POST.get(f"i{i.pk}", "").strip()
                if raw == "":
                    CountLine.objects.filter(count=c, item=i).delete()
                    continue
                try:
                    v = max(0, int(raw))
                except ValueError:
                    continue
                CountLine.objects.update_or_create(count=c, item=i, defaults={"qty": v})
                n += 1
        log_change(request.user, "Equipment", str(c), "counted", f"{n} items")
        s = count_summary(month)
        if s["missing"]:
            messages.warning(request, f"Count saved. {s['missing_pieces']} piece(s) missing – see the red lines.")
        else:
            messages.success(request, f"Count saved ({n} items).")
        return redirect(f"/equipment/count/?month={month:%Y-%m}")
    counted = {ln.item_id: ln.qty for ln in c.lines.all()} if c else {}
    groups = []
    for i in items:
        name = i.location.name if i.location else "No place set"
        if not groups or groups[-1][0] != name:
            groups.append((name, []))
        exp = i.expected_qty(month)
        got = counted.get(i.pk)
        groups[-1][1].append({"i": i, "exp": exp, "got": got, "short": (exp - got) if got is not None and got < exp else 0})
    prev = (month - datetime.timedelta(days=1)).replace(day=1)
    nxt = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return render(request, "equipment/count.html", {
        "month": month, "c": c, "groups": groups, "s": count_summary(month), "prev": prev,
        "next": nxt if nxt <= timezone.localdate().replace(day=1) else None,
        "sheet": request.GET.get("sheet") == "1", "loc": request.GET.get("loc", ""), "locs": Location.objects.all()})


@need("equipment", costs=True)
def depreciation(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
    except ValueError:
        year = today.year
    sch = year_schedule(datetime.date(year, 1, 1))
    month = today.replace(day=1)
    items = list(Item.objects.select_related("category"))
    return render(request, "equipment/depreciation.html", {
        "s": sch, "year": year, "cost": sum((i.total_cost for i in items if not i.disposed_on), Z),
        "book": sum((i.book_value(month) for i in items), Z), "month": month})


@need(owner=True)
def lists(request):
    cf = CategoryFormSet(request.POST or None, queryset=EquipmentCategory.objects.all(), prefix="c")
    lf = LocationFormSet(request.POST or None, queryset=Location.objects.all(), prefix="l")
    if request.method == "POST" and cf.is_valid() and lf.is_valid():
        cf.save()
        lf.save()
        log_change(request.user, "Equipment", "Categories & places", "changed")
        messages.success(request, "Saved.")
        return redirect("equipment:lists")
    return render(request, "equipment/lists.html", {"cf": cf, "lf": lf})
