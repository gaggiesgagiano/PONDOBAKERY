"""The SOP file: standard operating procedures – written by the Manager, approved by the Owner / Director,
read and signed by the staff. Job titles only, never names, so the file can be used by other shops too."""
import datetime

from django import forms
from django.contrib import messages
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import EDIT, VIEW, need
from .models import SOP_SECTIONS, Sop, SopRead, SopVersion, log_change
from .richtext import clean_doc


def _departments():
    from staff.models import DEPARTMENTS
    return [("all", "All staff")] + list(DEPARTMENTS)


class SopForm(forms.ModelForm):
    applies_list = forms.MultipleChoiceField(label="Must be read by", required=False, widget=forms.CheckboxSelectMultiple,
                                             help_text="Tick “All staff”, or the departments whose staff must read and sign it")
    note = forms.CharField(label="What changed (for the version history)", max_length=200, required=False)

    class Meta:
        model = Sop
        fields = ["section", "seq", "title", "purpose", "responsible", "body"]
        widgets = {"purpose": forms.Textarea(attrs={"rows": 2}),
                   "body": forms.Textarea(attrs={"rows": 4, "class": "rt-store"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["applies_list"].choices = _departments()
        self.fields["applies_list"].initial = self.instance.applies_keys() if self.instance.pk else ["all"]
        self.fields["seq"].help_text = "SOP 2.05 = section 2, number 5"

    def clean_body(self):
        html = clean_doc(self.cleaned_data.get("body", ""))
        if not html:
            raise forms.ValidationError("Type the procedure first.")
        return html

    def clean(self):
        cd = super().clean()
        if cd.get("section") and cd.get("seq"):
            dup = Sop.objects.filter(section=cd["section"], seq=cd["seq"], active=True).exclude(pk=self.instance.pk).first()
            if dup:
                self.add_error("seq", f"{dup.code} is already “{dup.title}”. Pick another number.")
        return cd


def _read_state(sop, people=None):
    """[(employee, read-or-None, 'ok'|'old'|'no')] for everybody who must read this SOP."""
    people = sop.readers() if people is None else people
    reads = {r.employee_id: r for r in sop.reads.all()}
    out = []
    for e in people:
        r = reads.get(e.pk)
        out.append((e, r, "no" if r is None else "ok" if r.version >= sop.version else "old"))
    return out


@need("sops", VIEW)
def sop_list(request):
    q = request.GET.get("q", "").strip()
    show_old = request.GET.get("old") == "1"
    qs = Sop.objects.all() if show_old else Sop.objects.filter(active=True)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(purpose__icontains=q) | Q(body__icontains=q) | Q(responsible__icontains=q))
    sops = list(qs.prefetch_related("reads"))
    from staff.models import Employee
    staff = [e for e in Employee.objects.filter(active=True) if not e.is_open]
    groups = []
    for num, name in SOP_SECTIONS:
        rows = []
        for s in sops:
            if s.section != num:
                continue
            keys = s.applies_keys()
            must = [e for e in staff if "all" in keys or not keys or e.department in keys]
            done = {r.employee_id for r in s.reads.all() if r.version >= s.version}
            s.n_must, s.n_done = len(must), sum(1 for e in must if e.pk in done)
            rows.append(s)
        if rows:
            groups.append({"num": num, "name": name, "rows": rows})
    today = timezone.localdate()
    counts = {"all": len(sops), "draft": sum(1 for s in sops if s.status == Sop.DRAFT),
              "review": sum(1 for s in sops if s.review_due and s.review_due <= today)}
    return render(request, "core/sops/list.html", {"groups": groups, "q": q, "counts": counts, "show_old": show_old, "today": today})


@need("sops", VIEW)
def sop_detail(request, pk):
    sop = get_object_or_404(Sop, pk=pk)
    state = _read_state(sop)
    return render(request, "core/sops/detail.html", {
        "sop": sop, "state": state, "today": timezone.localdate(),
        "n_ok": sum(1 for *_, st in state if st == "ok"), "versions": sop.versions.select_related("saved_by")})


def _changed(old, cd):
    return any(getattr(old, f) != cd[f] for f in ("title", "purpose", "responsible", "body"))


@need("sops", EDIT)
def sop_edit(request, pk=None):
    sop = get_object_or_404(Sop, pk=pk) if pk else None
    if request.method == "POST":
        before = Sop.objects.get(pk=sop.pk) if sop else None
        form = SopForm(request.POST, instance=sop or Sop())
        if form.is_valid():
            obj = form.save(commit=False)
            keys = form.cleaned_data["applies_list"] or ["all"]
            obj.applies = "all" if "all" in keys else ",".join(keys)
            obj.updated_by = request.user
            note = form.cleaned_data["note"]
            if before and before.status == Sop.APPROVED and _changed(before, form.cleaned_data):
                # an approved SOP changes: keep the old version, the new one is a draft until it is approved again
                SopVersion.objects.create(sop=before, version=before.version, title=before.title, purpose=before.purpose,
                                          responsible=before.responsible, body=before.body, approved_on=before.approved_on,
                                          approved_by=before.approved_by, saved_by=request.user, note=note)
                obj.version = before.version + 1
                obj.status, obj.approved_on = Sop.DRAFT, None
                messages.info(request, f"Version {before.version} is kept in the history. Version {obj.version} is a draft until it is approved.")
            obj.save()
            log_change(request.user, "SOP file", f"{obj.code} {obj.title}", "changed" if before else "added", note)
            messages.success(request, f"{obj.code} saved.")
            return redirect("core:sop", pk=obj.pk)
    else:
        init = {}
        if not sop:
            sec = int(request.GET.get("section", 1)) if request.GET.get("section", "").isdigit() else 1
            init = {"section": sec, "seq": (Sop.objects.filter(section=sec).aggregate(m=Max("seq"))["m"] or 0) + 1}
        form = SopForm(instance=sop or Sop(), initial=init)
    return render(request, "core/sops/form.html", {"form": form, "sop": sop})


@need("sops", EDIT)
@require_POST
def sop_approve(request, pk):
    sop = get_object_or_404(Sop, pk=pk)
    if request.POST.get("undo"):
        sop.status, sop.approved_on = Sop.DRAFT, None
        sop.save(update_fields=["status", "approved_on", "updated_at"])
        log_change(request.user, "SOP file", sop.code, "back to draft")
        messages.success(request, f"{sop.code} is a draft again.")
        return redirect("core:sop", pk=pk)
    try:
        d = datetime.date.fromisoformat(request.POST.get("approved_on", ""))
    except ValueError:
        d = timezone.localdate()
    sop.status, sop.approved_on = Sop.APPROVED, d
    sop.approved_by = (request.POST.get("approved_by") or sop.approved_by or "Owner / Director").strip()[:100]
    sop.save(update_fields=["status", "approved_on", "approved_by", "updated_at"])
    log_change(request.user, "SOP file", sop.code, "approved", f"{sop.approved_by} {d:%d %b %Y}")
    messages.success(request, f"{sop.code} version {sop.version} approved. Staff must now read and sign it.")
    return redirect("core:sop", pk=pk)


@need("sops", EDIT)
@require_POST
def sop_reads(request, pk):
    """Record who signed the paper sign-off sheet."""
    sop = get_object_or_404(Sop, pk=pk)
    try:
        d = datetime.date.fromisoformat(request.POST.get("signed_on", ""))
    except ValueError:
        d = timezone.localdate()
    ids = {int(x) for x in request.POST.getlist("emp") if x.isdigit()}
    allowed = {e.pk: e for e in sop.readers()}
    n = 0
    for i in ids & set(allowed):
        SopRead.objects.update_or_create(sop=sop, employee_id=i, defaults={"version": sop.version, "signed_on": d,
                                                                           "recorded_by": request.user})
        n += 1
    if n:
        log_change(request.user, "SOP file", sop.code, "signed by staff", f"{n} people, {d:%d %b %Y}")
        messages.success(request, f"{n} {'person' if n == 1 else 'people'} signed {sop.code} on {d:%d %b %Y}.")
    else:
        messages.error(request, "Tick the people who signed the sheet first.")
    return redirect("core:sop", pk=pk)


@need("sops", EDIT)
@require_POST
def sop_archive(request, pk):
    sop = get_object_or_404(Sop, pk=pk)
    sop.active = not sop.active
    sop.save(update_fields=["active", "updated_at"])
    log_change(request.user, "SOP file", sop.code, "taken out of the file" if not sop.active else "put back in the file")
    messages.success(request, f"{sop.code} {'taken out of the file' if not sop.active else 'is back in the file'}.")
    return redirect("core:sop", pk=pk) if sop.active else redirect("core:sops")


@need("sops", VIEW)
def sop_print(request):
    """The whole file (cover, contents, one SOP per page) – or one SOP with ?sop=…"""
    one = request.GET.get("sop")
    qs = Sop.objects.filter(active=True)
    if one:
        qs = qs.filter(pk=one)
    if request.GET.get("approved") == "1":
        qs = qs.filter(status=Sop.APPROVED)
    sops = list(qs)
    sections = [(n, name, [s for s in sops if s.section == n]) for n, name in SOP_SECTIONS]
    return render(request, "core/sops/print.html", {"sops": sops, "sections": [x for x in sections if x[2]], "one": bool(one),
                                                    "today": timezone.localdate()})


@need("sops", VIEW)
def sop_sheet(request, pk):
    """Paper sign-off sheet for one SOP – everybody who must read it, with space for signatures."""
    sop = get_object_or_404(Sop, pk=pk)
    return render(request, "core/sops/sheet.html", {"sop": sop, "people": sop.readers(), "today": timezone.localdate()})


@need("sops", VIEW)
def sop_staff(request):
    """Per staff member: which SOPs they still have to read (or read again after a change)."""
    from staff.models import DEPARTMENTS, Employee
    sops = list(Sop.objects.filter(active=True).prefetch_related("reads"))
    reads = {}
    for s in sops:
        for r in s.reads.all():
            reads[(s.pk, r.employee_id)] = r
    rows = []
    for e in Employee.objects.filter(active=True).order_by("department", "last_name", "first_name"):
        if e.is_open:
            continue
        must = [s for s in sops if "all" in s.applies_keys() or not s.applies_keys() or e.department in s.applies_keys()]
        todo, again = [], []
        for s in must:
            r = reads.get((s.pk, e.pk))
            if r is None:
                todo.append(s)
            elif r.version < s.version:
                again.append(s)
        rows.append({"e": e, "dept": dict(DEPARTMENTS).get(e.department, ""), "n": len(must), "done": len(must) - len(todo) - len(again),
                     "todo": todo, "again": again})
    return render(request, "core/sops/staff.html", {"rows": rows})
