import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import models, transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need, rights
from core.models import log_change

from .forms import (AdvanceForm, EmployeeForm, LeaveForm, NewPayRunForm, PaperForm, PayeBandFormSet, PayLineForm,
                    PayrollSettingsForm)
from .models import (DEPARTMENTS, Advance, Employee, LeaveRecord, PayeBand, PayLine, PayrollSettings, PayRun,
                     expiring_papers, file_checklist)
from .numbers import next_number
from .paycalc import band_list, work_out

Z = Decimal("0")


def month_end(d):
    return (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)


# ======================================================================= staff
@need("staff")
def staff_list(request):
    show = request.GET.get("show", "active")
    dept = request.GET.get("dept", "")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    qs = Employee.objects.all().prefetch_related("papers")
    if sort == "no":
        qs = qs.order_by("-active", models.Case(models.When(code="", then=1), default=0), "code", "first_name")
    else:
        # A–Z by the name everybody uses; open places (no name yet) at the bottom
        qs = qs.annotate(_open=models.Case(models.When(first_name="", known_as="", then=1), default=0),
                         _nm=Coalesce(NullIf("known_as", models.Value("")), "first_name"))
        qs = qs.order_by("-active", "_open", "_nm", "last_name")
    if show == "active":
        qs = qs.filter(active=True)
    elif show == "left":
        qs = qs.filter(active=False)
    if dept:
        qs = qs.filter(department=dept)
    if q:
        qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(known_as__icontains=q) | Q(middle_name__icontains=q) | Q(code__icontains=q) |
                       Q(id_number__icontains=q) | Q(job_title__icontains=q) | Q(phone__icontains=q))
    ps = PayrollSettings.get()
    needs, today = ps.needs, timezone.localdate()
    people = []
    for e in qs:
        items = [i for i in file_checklist(e, needs, list(e.papers.all()), today) if i["required"]]
        e.file_done = sum(1 for i in items if i["state"] == "both" and i["exp"] != "expired")
        e.file_items = items
        people.append(e)
    active = Employee.objects.filter(active=True)
    bill = sum((e.rate + e.allowances for e in active if e.pay_type == Employee.MONTHLY), Z)
    return render(request, "staff/staff_list.html", {
        "people": people, "show": show, "dept": dept, "depts": DEPARTMENTS, "q": q, "sort": sort, "n_active": active.exclude(first_name="", known_as="").count(),
        "n_open": active.filter(first_name="", known_as="").count(),
        "monthly_bill": bill, "n_day": active.exclude(pay_type=Employee.MONTHLY).count(), "n_needs": len(needs),
        "no_number": active.filter(code="").count(), "sample_no": next_number(ps),
        "expiring": expiring_papers(today), "today": today,
        "open_adv": Advance.objects.filter(recovered_in__isnull=True).aggregate(s=Sum("amount"))["s"] or Z})


@need("staff", EDIT)
def staff_edit(request, pk=None):
    e = get_object_or_404(Employee, pk=pk) if pk else Employee()
    form = EmployeeForm(request.POST or None, instance=e)
    if request.method == "POST" and form.is_valid():
        changed = ", ".join(form.changed_data)
        e = form.save(commit=False)
        if not e.code and e.active:
            e.code = next_number(start=e.start_date)
        e.save()
        log_change(request.user, "Staff", e.name, "changed" if pk else "added", changed if pk else e.code)
        if pk:
            messages.success(request, f"Saved {e.name}.")
            return redirect("staff:person", pk=e.pk)
        messages.success(request, f"Saved {e.name}{' as staff no. ' + e.code if e.code else ''}. Now add a photo and the papers for the staff file.")
        return redirect(reverse("staff:person", args=[e.pk]) + "#photo")
    return render(request, "staff/staff_form.html", {"form": form, "e": e})


@need("staff")
def staff_detail(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    lines = e.pay_lines.select_related("run").order_by("-run__period")[:24]
    today = timezone.localdate()
    papers = list(e.papers.select_related("added_by"))
    can = rights(request)
    checklist = file_checklist(e, PayrollSettings.get().needs, papers, today)
    req = [i for i in checklist if i["required"]]
    for p in papers:
        p.state = p.expiry_state(today)
        p.form = PaperForm(instance=p, auto_id=f"p{p.pk}_%s") if can.staff_edit else None
    return render(request, "staff/staff_detail.html", {
        "e": e, "lines": lines, "advances": e.advances.select_related("recovered_in__run", "given_by")[:30],
        "open_adv": e.open_advances().aggregate(s=Sum("amount"))["s"] or Z,
        "leave": e.leave.all()[:30], "balance": e.leave_balance(today),
        "papers": papers, "checklist": checklist, "file_done": sum(1 for i in req if i["state"] == "both" and i["exp"] != "expired"),
        "file_need": len(req), "paper_form": PaperForm(auto_id="new_%s"),
        "adv_form": AdvanceForm(initial={"date": today}), "leave_form": LeaveForm()})


@need("staff", EDIT)
@require_POST
def advance_add(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    form = AdvanceForm(request.POST)
    if form.is_valid():
        a = form.save(commit=False)
        a.employee, a.given_by = e, request.user
        a.save()
        log_change(request.user, "Staff", e.name, "advance given", f"${a.amount} {a.reason}")
        messages.success(request, f"Advance of ${a.amount:,.2f} saved. It comes off {e.first_name}'s next pay.")
    else:
        messages.error(request, "Advance not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
    return redirect("staff:person", pk=pk)


@need("staff", EDIT)
@require_POST
def advance_delete(request, pk):
    a = get_object_or_404(Advance, pk=pk, recovered_in__isnull=True)
    e = a.employee
    log_change(request.user, "Staff", e.name, "advance deleted", f"${a.amount}")
    a.delete()
    messages.success(request, "Advance deleted.")
    return redirect("staff:person", pk=e.pk)


@need("staff", EDIT)
@require_POST
def leave_add(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    form = LeaveForm(request.POST)
    if form.is_valid():
        lv = form.save(commit=False)
        lv.employee, lv.added_by = e, request.user
        lv.days = form.cleaned_data["days"]
        lv.save()
        log_change(request.user, "Staff", e.name, "leave added", f"{lv.get_kind_display()} {lv.start} – {lv.end} ({lv.days} days)")
        messages.success(request, f"{lv.get_kind_display()} saved: {lv.days.normalize()} days.")
    else:
        messages.error(request, "Leave not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
    return redirect("staff:person", pk=pk)


@need("staff", EDIT)
@require_POST
def leave_delete(request, pk):
    lv = get_object_or_404(LeaveRecord, pk=pk)
    e = lv.employee
    log_change(request.user, "Staff", e.name, "leave deleted", f"{lv.start} – {lv.end}")
    lv.delete()
    messages.success(request, "Leave deleted.")
    return redirect("staff:person", pk=e.pk)


# ======================================================================= payroll
def _settings_and_bands():
    return PayrollSettings.get(), band_list(PayeBand.objects.all())


def recalc_line(line, s, bands):
    work_out(line, s, bands, pays_nssa=line.employee.pays_nssa, pays_paye=line.employee.pays_paye)
    line.save()


def recalc_run(run):
    s, bands = _settings_and_bands()
    for ln in run.lines.select_related("employee"):
        recalc_line(ln, s, bands)


def _new_line(run, e, s, bands):
    end = month_end(run.period)
    adv = e.advances.filter(recovered_in__isnull=True, date__lte=end).aggregate(s=Sum("amount"))["s"] or Z
    ln = PayLine(run=run, employee=e, pay_type=e.pay_type, rate=e.rate, allowances=e.allowances, advances=adv)
    work_out(ln, s, bands, pays_nssa=e.pays_nssa, pays_paye=e.pays_paye)
    ln.save()
    return ln


@need("staff")
def payrun_list(request):
    runs = PayRun.objects.prefetch_related("lines")[:60]
    return render(request, "staff/payrun_list.html", {"rows": [(r, r.totals()) for r in runs], "form": NewPayRunForm(),
                                                      "s": PayrollSettings.get(), "no_bands": not PayeBand.objects.exists()})


@need("staff", EDIT)
@require_POST
def payrun_new(request):
    form = NewPayRunForm(request.POST)
    if not form.is_valid():
        runs = PayRun.objects.prefetch_related("lines")[:60]
        return render(request, "staff/payrun_list.html", {"rows": [(r, r.totals()) for r in runs], "form": form,
                                                          "s": PayrollSettings.get()})
    period = form.cleaned_data["month"]
    s, bands = _settings_and_bands()
    with transaction.atomic():
        run = PayRun.objects.create(period=period, pay_date=form.cleaned_data["pay_date"], created_by=request.user)
        end = month_end(period)
        people = (Employee.objects.filter(start_date__lte=end).filter(Q(active=True) | Q(end_date__gte=period))
                  .exclude(first_name="", known_as=""))  # open places are not paid
        for e in people:
            _new_line(run, e, s, bands)
    log_change(request.user, "Payroll", str(run), "pay run started", f"{run.lines.count()} people")
    if not run.lines.exists():
        messages.info(request, "Nobody to pay yet – add your staff first under Staff.")
    return redirect("staff:payrun_edit", pk=run.pk)


@need("staff", EDIT)
def payrun_edit(request, pk):
    run = get_object_or_404(PayRun, pk=pk)
    if run.status != PayRun.DRAFT:
        messages.error(request, "This pay run is final. The Operations Manager can re-open it if something must change.")
        return redirect("staff:payrun", pk=pk)
    lines = list(run.lines.select_related("employee"))
    if request.method == "POST":
        forms = [PayLineForm(request.POST, prefix=f"l{ln.pk}", line=ln) for ln in lines]
        if all(f.is_valid() for f in forms):
            s, bands = _settings_and_bands()
            with transaction.atomic():
                for f, ln in zip(forms, lines):
                    cd = f.cleaned_data
                    if cd.get("remove"):
                        ln.delete()
                        continue
                    for k in ("days", "hours"):
                        setattr(ln, k, cd.get(k))
                    for k in ("unpaid_days", "overtime_hours", "holiday_hours", "allowances", "bonus", "other_earnings",
                              "advances", "other_deductions"):
                        setattr(ln, k, cd.get(k) or Z)
                    ln.deduction_note = cd.get("deduction_note", "")
                    recalc_line(ln, s, bands)
                for epk in request.POST.getlist("add"):
                    e = Employee.objects.filter(pk=epk).first()
                    if e and not run.lines.filter(employee=e).exists():
                        _new_line(run, e, s, bands)
                run.pay_date = request.POST.get("pay_date") or run.pay_date
                run.notes = request.POST.get("notes", "")[:2000]
                run.save()
            log_change(request.user, "Payroll", str(run), "pay run saved")
            negative = [ln.employee.first_name for ln in run.lines.select_related("employee") if ln.net < 0]
            if negative:
                messages.warning(request, "Pay run saved – but these people end up with less than $0: " + ", ".join(negative)
                                 + ". Take off less advance this month.")
            else:
                messages.success(request, "Pay run saved.")
            if request.POST.get("stay"):
                return redirect("staff:payrun_edit", pk=run.pk)
            return redirect("staff:payrun", pk=run.pk)
    else:
        forms = [PayLineForm(prefix=f"l{ln.pk}", line=ln, initial={
            "days": ln.days, "hours": ln.hours, "unpaid_days": ln.unpaid_days or None, "overtime_hours": ln.overtime_hours or None,
            "holiday_hours": ln.holiday_hours or None, "allowances": ln.allowances or None, "bonus": ln.bonus or None,
            "other_earnings": ln.other_earnings or None, "advances": ln.advances or None,
            "other_deductions": ln.other_deductions or None, "deduction_note": ln.deduction_note}) for ln in lines]
    in_run = {ln.employee_id for ln in lines}
    missing = [e for e in Employee.objects.filter(active=True) if e.pk not in in_run and not e.is_open]
    return render(request, "staff/payrun_form.html", {"run": run, "rows": list(zip(lines, forms)), "missing": missing,
                                                      "s": PayrollSettings.get(), "t": run.totals()})


@need("staff")
def payrun_detail(request, pk):
    run = get_object_or_404(PayRun.objects.select_related("created_by"), pk=pk)
    lines = list(run.lines.select_related("employee"))
    return render(request, "staff/payrun_detail.html", {"run": run, "lines": lines, "t": run.totals(),
                                                        "s": PayrollSettings.get()})


def _recover_advances(line):
    """Mark the worker's open advances as taken off this pay line (splitting one if only part is taken)."""
    left = line.advances
    end = month_end(line.run.period)
    for a in line.employee.advances.filter(recovered_in__isnull=True, date__lte=end).order_by("date", "id"):
        if left <= 0:
            break
        if a.amount <= left:
            a.recovered_in = line
            a.save(update_fields=["recovered_in"])
            left -= a.amount
        else:  # only part of this advance is taken off now – split it
            Advance.objects.create(employee=a.employee, date=a.date, amount=left, reason=a.reason, given_by=a.given_by,
                                   recovered_in=line)
            a.amount -= left
            a.save(update_fields=["amount"])
            left = Z


@need("staff", EDIT)
@require_POST
def payrun_status(request, pk):
    run = get_object_or_404(PayRun, pk=pk)
    to = request.POST.get("to")
    if to == "final" and run.status == PayRun.DRAFT:
        neg = [ln for ln in run.lines.select_related("employee") if ln.net < 0]
        if neg:
            messages.error(request, "Fix the people with less than $0 pay first.")
            return redirect("staff:payrun", pk=pk)
        with transaction.atomic():
            recalc_run(run)
            for ln in run.lines.select_related("employee", "run"):
                if ln.advances > 0:
                    _recover_advances(ln)
            run.status, run.finalized_at = PayRun.FINAL, timezone.now()
            run.save()
        log_change(request.user, "Payroll", str(run), "made final", f"net ${run.totals()['net']}")
        messages.success(request, "Pay run is final. Advances taken off are marked as paid back. Print the payslips.")
    elif to == "draft" and run.status == PayRun.FINAL:
        if not rights(request).owner:
            messages.error(request, "Only the Operations Manager can re-open a final pay run.")
        else:
            with transaction.atomic():
                Advance.objects.filter(recovered_in__run=run).update(recovered_in=None)
                run.status, run.finalized_at = PayRun.DRAFT, None
                run.save()
            log_change(request.user, "Payroll", str(run), "re-opened")
            messages.success(request, "Pay run re-opened. Advances are open again until you make it final.")
    return redirect("staff:payrun", pk=pk)


@need("staff", EDIT)
@require_POST
def payrun_delete(request, pk):
    run = get_object_or_404(PayRun, pk=pk, status=PayRun.DRAFT)
    name = str(run)
    run.delete()
    log_change(request.user, "Payroll", name, "deleted")
    messages.success(request, f"{name} deleted.")
    return redirect("staff:payruns")


def _ytd(line):
    """Year-to-date totals from final pay runs in the same year, up to and including this one."""
    qs = PayLine.objects.filter(employee=line.employee, run__period__year=line.run.period.year,
                                run__period__lte=line.run.period).filter(Q(run__status=PayRun.FINAL) | Q(pk=line.pk))
    return qs.aggregate(gross=Sum("gross"), paye=Sum("paye"), aids=Sum("aids_levy"), nssa=Sum("nssa"), net=Sum("net"))


@need("staff")
def payslips(request, pk, emp=None):
    run = get_object_or_404(PayRun, pk=pk)
    lines = run.lines.select_related("employee")
    if emp:
        lines = lines.filter(employee_id=emp)
    today = timezone.localdate()
    slips = [{"ln": ln, "ytd": _ytd(ln), "leave": ln.employee.leave_balance(min(today, month_end(run.period)))}
             for ln in lines]
    return render(request, "staff/print_payslips.html", {"run": run, "slips": slips, "s": PayrollSettings.get()})


@need("staff")
def payrun_summary(request, pk):
    run = get_object_or_404(PayRun, pk=pk)
    return render(request, "staff/print_summary.html", {"run": run, "lines": run.lines.select_related("employee"),
                                                        "t": run.totals(), "s": PayrollSettings.get()})


@need(owner=True)
def payroll_settings(request):
    s = PayrollSettings.get()
    sf = PayrollSettingsForm(request.POST or None, instance=s)
    bf = PayeBandFormSet(request.POST or None, queryset=PayeBand.objects.all(), prefix="b")
    if request.method == "POST" and sf.is_valid() and bf.is_valid():
        kept = [f for f in bf.forms if f.has_changed() or f.instance.pk]
        kept = [f for f in kept if not f.cleaned_data.get("DELETE") and (f.instance.pk or f.has_changed())]
        tops = [f for f in kept if f.cleaned_data.get("up_to") is None]
        if not kept:
            messages.error(request, "Keep at least one tax band.")
        elif len(tops) != 1:
            messages.error(request, "Exactly one band must have an empty 'Pay up to' (the top band).")
        else:
            with transaction.atomic():
                sf.save()
                bf.save()
                drafts = list(PayRun.objects.filter(status=PayRun.DRAFT))
                for run in drafts:
                    recalc_run(run)
            log_change(request.user, "Payroll", "Payroll settings", "changed")
            messages.success(request, "Payroll settings saved." + (f" {len(drafts)} draft pay run(s) worked out again." if drafts else ""))
            return redirect("staff:settings")
    return render(request, "staff/settings.html", {"sf": sf, "bf": bf, "s": s})
