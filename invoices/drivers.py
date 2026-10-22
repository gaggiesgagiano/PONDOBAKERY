"""Delivery drivers: the list, each driver's page with photo and car photo, and the driver ID card.

Photos are kept with the staff files (private, only for people with sales rights) – never as a public link.
"""
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.access import EDIT, need
from core.models import log_change
from staff.files import MAX_PHOTO, PHOTO_TYPES, _ext, _is_picture, _send

from .forms import DriverForm
from .models import Delivery, Driver

Z = Decimal("0")
WHICH = {"driver": "photo", "car": "car_photo"}


def _short_by_driver():
    """Money each driver brought back short (minus) or over, over all checked-off cash deliveries."""
    out = {}
    for d in Delivery.objects.filter(status=Delivery.DONE, pay=Delivery.DRIVER, money_back__isnull=False):
        if d.driver_id:
            out[d.driver_id] = out.get(d.driver_id, Z) + (d.money_back - d.goods)
    return out


@need("deliveries")
def driver_list(request):
    show = request.GET.get("show", "active")
    q = request.GET.get("q", "").strip()
    qs = Driver.objects.annotate(n=Count("deliveries", filter=~Q(deliveries__status=Delivery.CANCELLED)),
                                 last=Max("deliveries__date"))
    if show == "active":
        qs = qs.filter(active=True)
    elif show == "stopped":
        qs = qs.filter(active=False)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(car_reg__icontains=q) | Q(id_number__icontains=q))
    short = _short_by_driver()
    rows = list(qs)
    for d in rows:
        d.short = short.get(d.pk)
    return render(request, "invoices/drivers.html", {"rows": rows, "show": show, "q": q,
                                                     "no_photo": sum(1 for d in rows if not d.photo)})


@need("deliveries", EDIT)
def driver_edit(request, pk=None):
    drv = get_object_or_404(Driver, pk=pk) if pk else Driver()
    form = DriverForm(request.POST or None, instance=drv)
    if request.method == "POST" and form.is_valid():
        drv = form.save()
        log_change(request.user, "Drivers", drv.name, "changed" if pk else "added", ", ".join(form.changed_data))
        messages.success(request, f"Saved {drv.name}." + ("" if pk else " Now take his photo and the car's photo."))
        return redirect(reverse("invoices:driver", args=[drv.pk]) + ("" if pk else "#photo"))
    return render(request, "invoices/driver_form.html", {"form": form, "drv": drv})


@need("deliveries")
def driver_detail(request, pk):
    drv = get_object_or_404(Driver, pk=pk)
    dels = list(drv.deliveries.select_related("doc").order_by("-date", "-id")[:30])
    short = _short_by_driver().get(drv.pk)
    return render(request, "invoices/driver_detail.html", {"drv": drv, "dels": dels, "short": short,
                                                           "n": drv.deliveries.exclude(status=Delivery.CANCELLED).count()})


@need("deliveries")
def driver_photo(request, pk, which):
    drv = get_object_or_404(Driver, pk=pk)
    if which not in WHICH:
        raise Http404
    f = getattr(drv, WHICH[which])
    return _send(f, f"{drv.number} {drv.name} {which}{_ext(f.name) if f else ''}", cache="private, max-age=86400")


@need("deliveries", EDIT)
@require_POST
def driver_photo_change(request, pk, which):
    drv = get_object_or_404(Driver, pk=pk)
    if which not in WHICH:
        raise Http404
    field = WHICH[which]
    current = getattr(drv, field)
    old = current.name if current else ""
    back = redirect(reverse("invoices:driver", args=[pk]) + ("#photo" if which == "driver" else "#car"))
    if request.POST.get("remove"):
        setattr(drv, field, "")
        msg = "Photo removed."
    else:
        f = request.FILES.get("photo")
        if not f:
            messages.error(request, "Choose a photo first.")
            return back
        if _ext(f.name) not in PHOTO_TYPES or not _is_picture(f):
            messages.error(request, "That is not a photo. Use a JPG or PNG picture.")
            return back
        if f.size > MAX_PHOTO:
            messages.error(request, "That photo is too big (over 15 MB).")
            return back
        drv._which = "car" if which == "car" else "photo"
        getattr(drv, field).save(f"{which}{_ext(f.name)}", f, save=False)
        msg = "Photo saved."
    drv.save()
    new = getattr(drv, field)
    if old and old != (new.name if new else ""):
        try:
            current.storage.delete(old)
        except OSError:
            pass
    log_change(request.user, "Drivers", drv.name, f"{which} photo " + ("removed" if request.POST.get("remove") else "changed"))
    messages.success(request, msg)
    return back


@need("deliveries")
def driver_cards(request, pk=None):
    if pk:
        people = [get_object_or_404(Driver, pk=pk)]
    else:
        ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
        people = list(Driver.objects.filter(pk__in=ids) if ids else Driver.objects.filter(active=True))
    pages = [people[i:i + 4] for i in range(0, len(people), 4)] or [[]]
    return render(request, "invoices/driver_cards.html", {"pages": pages})
