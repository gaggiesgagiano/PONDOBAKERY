import datetime
import json

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import need, rights
from core.models import log_change

from .calc import month_end, snapshot, stock_results
from .models import MonthClose


def _month(request, default_last=False):
    today = timezone.localdate()
    try:
        return datetime.date.fromisoformat(request.GET.get("month", "") + "-01")
    except ValueError:
        first = today.replace(day=1)
        # like the Excel sheet: in the first days of a month, open last month
        if default_last and today.day <= 7:
            return (first - datetime.timedelta(days=1)).replace(day=1)
        return first


def _nav(month):
    today = timezone.localdate()
    prev = (month - datetime.timedelta(days=1)).replace(day=1)
    nxt = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return {"prev": prev, "next": nxt if nxt <= today.replace(day=1) else None}


@need(costs=True)
def month_end_view(request):
    month = _month(request, default_last=True)
    m = month_end(month)
    closed = MonthClose.objects.filter(month=month).first()
    return render(request, "reports/month_end.html", {"m": m, "closed": closed, **_nav(month)})


@need(costs=True)
def month_end_print(request):
    month = _month(request, default_last=True)
    m = month_end(month)
    # keep the page short: the 12 biggest suppliers / expense types, the rest on one line
    def top(rows, n=12):
        if len(rows) <= n + 1:
            return rows, None
        return rows[:n - 1], (len(rows) - n + 1, sum((v for _, v in rows[n - 1:]), 0))
    sup, sup_other = top(m["by_supplier"])
    cat, cat_other = top(m["by_cat"], 16)
    return render(request, "print/month_end.html", {"m": m, "sup": sup, "sup_other": sup_other, "cat": cat,
                                                    "cat_other": cat_other,
                                                    "closed": MonthClose.objects.filter(month=month).first()})


@need(costs=True)
def stock_results_view(request):
    month = _month(request)
    return render(request, "reports/stock_results.html", {"r": stock_results(month), "month": month, **_nav(month)})


@need(costs=True)
def archive_view(request):
    rows = list(MonthClose.objects.select_related("locked_by"))
    return render(request, "reports/archive.html", {"rows": rows})


@need(owner=True)
@require_POST
def lock_month(request):
    try:
        month = datetime.date.fromisoformat(request.POST.get("month", ""))
    except ValueError:
        return redirect("reports:month_end")
    mc, created = MonthClose.objects.get_or_create(month=month, defaults={"locked_by": request.user})
    mc.figures_json = json.dumps(snapshot(month_end(month)))
    mc.locked_by = request.user
    mc.save()
    log_change(request.user, "Reports", f"{month:%B %Y}", "month locked" if created else "month locked again")
    messages.success(request, f"{month:%B %Y} is locked in the Month archive.")
    return redirect(f"/reports/?month={month:%Y-%m}")


@need(owner=True)
@require_POST
def archive_edit(request, pk):
    mc = get_object_or_404(MonthClose, pk=pk)
    if request.POST.get("delete"):
        name = str(mc)
        mc.delete()
        log_change(request.user, "Reports", name, "month unlocked")
        messages.success(request, f"{name} taken out of the archive.")
    else:
        mc.sent_to_accountant = request.POST.get("sent_to_accountant", "")[:80]
        mc.notes = request.POST.get("notes", "")[:2000]
        mc.save()
        messages.success(request, f"{mc} saved.")
    return redirect("reports:archive")
