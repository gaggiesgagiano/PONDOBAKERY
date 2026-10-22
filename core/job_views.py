"""Choose which jobs show under Today's jobs, in which order – and add your own jobs to tick off each day."""
import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import rights
from .areas import ITEMS, menu
from .jobs import JOBS, available, chosen
from .models import MyJob, MyJobDone, UserLook, log_change


def _look(user):
    look, _ = UserLook.objects.get_or_create(user=user)
    return look


@login_required
def jobs_choose(request):
    can = rights(request)
    if request.method == "POST":
        allowed = [k for k, *_ in available(can, request.user)]
        order = [k for k in request.POST.get("order", "").split(",") if k in allowed]
        order += [k for k in allowed if k not in order]
        on = set(request.POST.getlist("on"))
        keys = [k for k in order if k in on]
        look = _look(request.user)
        look.jobs = ",".join(k if k in on else "!" + k for k in order)
        look.save(update_fields=["jobs"])
        messages.success(request, f"Saved – {len(keys)} job{'s' if len(keys) != 1 else ''} on your dashboard.")
        return redirect("core:dashboard")
    from .jobs import saved_order

    current = chosen(can, request.user)
    rows = {k: (k, name, about, kind, mj) for k, name, about, kind, mj in available(can, request.user)}
    saved = [k for k, _ in (saved_order(request.user) or [])]
    first = current + [k for k in saved if k not in current]
    ordered = [rows[k] for k in first if k in rows] + [r for k, r in rows.items() if k not in first]
    items = []
    for k, name, about, kind, mj in ordered:
        if kind == "program":
            area = {"cashup": "sales", "plan": "production", "receiving": "stock", "low_stock": "stock",
                    "orders": "stock", "stocktake": "stock", "staff_papers": "staff", "quotes": "invoices",
                    "payroll": "staff", "month_end": "reports", "price_change": "prices"}.get(k, k)
            colour = ITEMS.get(area, ITEMS["dashboard"])[2]
        else:
            colour = mj.colour
        items.append({"key": k, "name": name, "about": about, "kind": kind, "mj": mj, "on": k in current,
                      "colour": colour, "mine": bool(mj and (mj.user_id == request.user.pk or can.owner))})
    return render(request, "core/jobs_choose.html", {"items": items, "form": MyJobForm(can=can)})


@login_required
@require_POST
def jobs_reset(request):
    look = _look(request.user)
    look.jobs = ""
    look.save(update_fields=["jobs"])
    messages.success(request, "Back to the standard list of jobs.")
    return redirect("core:jobs")


class MyJobForm(forms.ModelForm):
    days_list = forms.MultipleChoiceField(label="Which days", choices=MyJob.DAYS, widget=forms.CheckboxSelectMultiple,
                                          initial=[d for d, _ in MyJob.DAYS])

    class Meta:
        model = MyJob
        fields = ["title", "note", "link", "colour", "shared"]
        widgets = {"colour": forms.RadioSelect, "title": forms.TextInput(attrs={"placeholder": "e.g. Clean the display fridges"}),
                   "note": forms.TextInput(attrs={"placeholder": "e.g. before 7 am"})}

    def __init__(self, *a, can=None, **kw):
        super().__init__(*a, **kw)
        pages = [("", "– no page, just tick it off –")]
        for g in menu(can, None) if can else []:
            pages += [(it["key"], it["label"]) for it in g["items"]]
        self.fields["link"] = forms.ChoiceField(label="Clicking it opens", choices=pages, required=False)
        if self.instance.pk:
            self.fields["days_list"].initial = list(self.instance.days)
        if not (can and can.owner):
            del self.fields["shared"]

    def clean_days_list(self):
        days = self.cleaned_data["days_list"]
        if not days:
            raise forms.ValidationError("Tick at least one day.")
        return days

    def save(self, commit=True):
        self.instance.days = "".join(sorted(self.cleaned_data["days_list"]))
        return super().save(commit)


@login_required
def my_job_edit(request, pk=None):
    can = rights(request)
    mj = None
    if pk:
        mj = get_object_or_404(MyJob, pk=pk)
        if mj.user_id != request.user.pk and not can.owner:
            messages.error(request, "Only the person who added this job (or the Manager) can change it.")
            return redirect("core:jobs")
    form = MyJobForm(request.POST or None, instance=mj or MyJob(user=request.user), can=can)
    if request.method == "POST" and form.is_valid():
        new = form.save()
        if not pk:  # put it on the dashboard straight away
            look = _look(request.user)
            if look.jobs.strip():
                look.jobs = look.jobs + "," + new.key
                look.save(update_fields=["jobs"])
        log_change(request.user, "Today's jobs", new.title, "changed" if pk else "added", new.days_text)
        messages.success(request, f"Saved “{new.title}”.")
        return redirect("core:jobs")
    return render(request, "core/my_job_form.html", {"form": form, "mj": mj})


@login_required
@require_POST
def my_job_delete(request, pk):
    mj = get_object_or_404(MyJob, pk=pk)
    if mj.user_id != request.user.pk and not rights(request).owner:
        messages.error(request, "Only the person who added this job (or the Manager) can delete it.")
    else:
        log_change(request.user, "Today's jobs", mj.title, "deleted")
        mj.delete()
        messages.success(request, "Job deleted.")
    return redirect("core:jobs")


@login_required
@require_POST
def my_job_tick(request, pk):
    mj = get_object_or_404(MyJob, pk=pk)
    if mj.user_id != request.user.pk and not mj.shared:
        return redirect("core:dashboard")
    try:
        d = datetime.date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        d = timezone.localdate()
    tick = MyJobDone.objects.filter(job=mj, date=d).first()
    if tick:
        tick.delete()
    else:
        MyJobDone.objects.create(job=mj, date=d, by=request.user)
        if mj.shared:
            log_change(request.user, "Today's jobs", mj.title, "done", f"{d:%d %b %Y}")
    nxt = request.POST.get("next") or ""
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "core:dashboard")


@login_required
@require_POST
def jobs_order(request):
    """Dashboard drag & drop: the tiles shown today, in their new order. Jobs not shown today
    (hidden, or not due today) keep their place in between."""
    from .jobs import saved_order

    can = rights(request)
    allowed = [k for k, *_ in available(can, request.user)]
    moved = [k for k in request.POST.get("order", "").split(",") if k in allowed]
    moved = list(dict.fromkeys(moved))
    if not moved:
        return JsonResponse({"ok": False}, status=400)
    on_keys = chosen(can, request.user)
    hidden = [k for k, on in (saved_order(request.user) or []) if not on and k in allowed and k not in on_keys]
    full = on_keys + [k for k in hidden if k not in on_keys]
    full += [k for k in moved if k not in full]
    slots = iter(moved)
    new = [next(slots) if k in moved else k for k in full]
    look = _look(request.user)
    look.jobs = ",".join(k if k in on_keys or k in moved else "!" + k for k in new)
    look.save(update_fields=["jobs"])
    return JsonResponse({"ok": True})
