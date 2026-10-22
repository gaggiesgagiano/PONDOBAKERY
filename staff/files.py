"""The staff file: photo, personal papers (soft copy on the laptop, hard copy in the paper file), staff numbers,
the staff file cover sheet and staff cards.

Photos and papers are only handed out to people who are logged in with staff rights. They have no public link.
"""
import os

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need, rights
from core.models import log_change

from .forms import PaperForm, StaffFileSettingsForm
from .models import CHECKLIST, DEPARTMENTS, Employee, PayrollSettings, StaffPaper, expiring_papers, file_checklist
from .numbers import fmt, lead, next_number, number_everyone

PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PAPER_TYPES = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".tif", ".tiff", ".bmp",
               ".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx"}
# shown in the browser; everything else is downloaded and opens in its own program (Word, Excel …)
INLINE = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
          ".webp": "image/webp", ".gif": "image/gif", ".txt": "text/plain; charset=utf-8"}
MAX_PHOTO = 15 * 1024 * 1024
MAX_PAPER = 25 * 1024 * 1024


def _ext(name):
    return os.path.splitext(name or "")[1].lower()


def _is_picture(f):
    head = f.read(16)
    f.seek(0)
    return (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG\r\n\x1a\n") or head[:6] in (b"GIF87a", b"GIF89a")
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def _send(fieldfile, filename, download=False, cache="private, no-store"):
    if not fieldfile:
        raise Http404
    try:
        fh = fieldfile.storage.open(fieldfile.name, "rb")
    except (FileNotFoundError, OSError):
        raise Http404
    ext = _ext(filename) or _ext(fieldfile.name)
    inline = ext in INLINE and not download
    resp = FileResponse(fh, as_attachment=not inline, filename=filename,
                        content_type=INLINE.get(ext, "application/octet-stream"))
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = cache
    return resp


def _back(e, anchor=""):
    return redirect(reverse("staff:person", args=[e.pk]) + anchor)


# ======================================================================= photo
@need("staff")
def photo(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    return _send(e.photo, f"{e.code or e.pk} {e.name}{_ext(e.photo.name) if e.photo else ''}",
                 cache="private, max-age=86400")


@need("staff", EDIT)
@require_POST
def photo_change(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    old = e.photo.name if e.photo else ""
    if request.POST.get("remove"):
        e.photo = ""
        e.save(update_fields=["photo", "updated_at"])
        msg = "Photo removed."
    else:
        f = request.FILES.get("photo")
        if not f:
            messages.error(request, "Choose a photo first.")
            return _back(e, "#photo")
        if _ext(f.name) not in PHOTO_TYPES or not _is_picture(f):
            messages.error(request, "That is not a photo. Use a JPG or PNG picture.")
            return _back(e, "#photo")
        if f.size > MAX_PHOTO:
            messages.error(request, "That photo is too big (over 15 MB).")
            return _back(e, "#photo")
        e.photo.save(f"photo{_ext(f.name)}", f, save=False)
        e.save(update_fields=["photo", "updated_at"])
        msg = "Photo saved."
    if old and old != e.photo.name:
        try:
            e.photo.storage.delete(old)
        except OSError:
            pass
    log_change(request.user, "Staff", e.name, "photo " + ("removed" if request.POST.get("remove") else "changed"))
    messages.success(request, msg)
    return _back(e)


# ======================================================================= papers
@need("staff", EDIT)
@require_POST
def paper_add(request, pk):
    e = get_object_or_404(Employee, pk=pk)
    form = PaperForm(request.POST)
    files = request.FILES.getlist("files")
    if not form.is_valid():
        messages.error(request, "Not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
        return _back(e, "#papers")
    cd = form.cleaned_data
    if not files and not cd["hard_copy"]:
        messages.error(request, "Choose the scan or photo of the paper – or tick that the paper copy is in the file.")
        return _back(e, "#papers")
    bad = [f.name for f in files if _ext(f.name) not in PAPER_TYPES]
    if bad:
        messages.error(request, f"Not saved: {', '.join(bad)} can't be added. Use PDF, a photo (JPG / PNG) or a Word file.")
        return _back(e, "#papers")
    big = [f.name for f in files if f.size > MAX_PAPER]
    if big:
        messages.error(request, f"Not saved: {', '.join(big)} is bigger than 25 MB. Scan it at a lower quality.")
        return _back(e, "#papers")
    made = []
    with transaction.atomic():
        n = len(files)
        for i, f in enumerate(files or [None], 1):
            title = cd["title"]
            if n > 1:  # e.g. an ID front and back: "page 1 of 2", "page 2 of 2"
                title = f"{title} ({i} of {n})" if title else f"page {i} of {n}"
            p = StaffPaper(employee=e, kind=cd["kind"], title=title[:120], hard_copy=cd["hard_copy"],
                           expires=cd["expires"], notes=cd["notes"], added_by=request.user)
            if f:
                p.original_name, p.size = os.path.basename(f.name)[:200], f.size
                p.file.save(f.name, f, save=False)
            p.save()
            made.append(p)
    what = made[0].get_kind_display()
    log_change(request.user, "Staff", e.name, "paper added",
               f"{what}{' – ' + cd['title'] if cd['title'] else ''} ({n} file{'s' if len(files) != 1 else ''}"
               f"{', paper copy in file' if cd['hard_copy'] else ''})")
    if files:
        messages.success(request, f"{what} saved ({len(files)} file{'s' if len(files) != 1 else ''})."
                         + ("" if cd["hard_copy"] else " Tick “In the file” once the paper copy is in the staff file."))
    else:
        messages.success(request, f"{what} noted as being in the paper file. Add the scan later with “+ Add papers”.")
    return _back(e, "#papers")


@need("staff")
def paper_open(request, pk):
    p = get_object_or_404(StaffPaper, pk=pk)
    e = p.employee
    name = f"{e.code + ' ' if e.code else ''}{e.name} - {p.get_kind_display()}{_ext(p.original_name or p.file.name)}"
    return _send(p.file, name.replace("/", "-"), download=request.GET.get("download") == "1")


@need("staff", EDIT)
@require_POST
def paper_edit(request, pk):
    p = get_object_or_404(StaffPaper, pk=pk)
    form = PaperForm(request.POST, instance=p)
    if form.is_valid():
        changed = ", ".join(form.changed_data)
        form.save()
        log_change(request.user, "Staff", p.employee.name, "paper changed", f"{p.get_kind_display()}: {changed}")
        messages.success(request, f"{p.get_kind_display()} saved.")
    else:
        messages.error(request, "Not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
    return _back(p.employee, "#papers")


@need("staff", EDIT)
@require_POST
def paper_hard(request, pk):
    p = get_object_or_404(StaffPaper, pk=pk)
    p.hard_copy = not p.hard_copy
    p.save(update_fields=["hard_copy"])
    log_change(request.user, "Staff", p.employee.name, "paper copy " + ("in file" if p.hard_copy else "not in file"),
               p.get_kind_display())
    return _back(p.employee, "#papers")


@need("staff", EDIT)
@require_POST
def paper_delete(request, pk):
    p = get_object_or_404(StaffPaper, pk=pk)
    e = p.employee
    log_change(request.user, "Staff", e.name, "paper deleted", f"{p.get_kind_display()} {p.original_name}")
    p.delete()
    messages.success(request, "Deleted from the laptop. The paper copy in the file is not affected.")
    return _back(e, "#papers")


# ======================================================================= overview & settings
def _rows(people, needs, today):
    rows = []
    for e in people:
        items = file_checklist(e, needs, list(e.papers.all()), today)
        cells = {i["key"]: i for i in items}
        req = [cells[k] for k, _, _ in CHECKLIST if k in needs]
        done = sum(1 for i in req if i["state"] == "both" and i["exp"] != "expired")
        rows.append({"e": e, "cells": req, "done": done, "complete": done == len(req) and bool(e.photo),
                     "extra": [i for i in items if not i["required"]]})
    return rows


@need("staff")
def overview(request):
    s = PayrollSettings.get()
    today = timezone.localdate()
    people = Employee.objects.filter(active=True).prefetch_related("papers").order_by("code", "first_name")
    rows = _rows(people, s.needs, today)
    can = rights(request)
    form = StaffFileSettingsForm(instance=s) if can.staff_edit else None
    return render(request, "staff/files.html", {
        "rows": rows, "columns": [(k, label) for k, label, _ in CHECKLIST if k in s.needs], "s": s, "form": form,
        "expiring": expiring_papers(today), "today": today,
        "n_complete": sum(1 for r in rows if r["complete"]), "n_photo": sum(1 for r in rows if not r["e"].photo),
        "no_number": [r["e"] for r in rows if not r["e"].code],
        "next_no": next_number(s)})


@need("staff", EDIT)
@require_POST
def file_settings(request):
    s = PayrollSettings.get()
    form = StaffFileSettingsForm(request.POST, instance=s)
    if form.is_valid():
        form.save()
        log_change(request.user, "Staff", "Staff file settings", "changed",
                   f"numbers like {fmt(lead(s), s.staff_no_digits, 1)}, file needs {s.file_needs}")
        messages.success(request, "Saved.")
    else:
        messages.error(request, "Not saved: " + " ".join(m for errs in form.errors.values() for m in errs))
    return redirect("staff:files")


@need("staff", EDIT)
@require_POST
def give_numbers(request):
    done = number_everyone()
    if done:
        log_change(request.user, "Staff", "Staff numbers", "given",
                   ", ".join(f"{e.code} {e.name}" for e in done)[:500])
        messages.success(request, f"{len(done)} staff member{'s' if len(done) != 1 else ''} now ha{'ve' if len(done) != 1 else 's'} "
                         f"a number: {done[0].code} to {done[-1].code}. You can change any number on the person's “Edit” page.")
    else:
        messages.success(request, "Everybody already has a number.")
    return redirect(request.POST.get("next") or "staff:files")


# ======================================================================= prints
def _picked(request, pk=None):
    if pk:
        return [get_object_or_404(Employee, pk=pk)]
    ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
    qs = Employee.objects.filter(pk__in=ids) if ids else Employee.objects.filter(active=True)
    return list(qs.prefetch_related("papers").order_by("code", "first_name"))


@need("staff")
def print_file(request, pk=None):
    """The cover sheet for the front of each paper staff file."""
    s = PayrollSettings.get()
    today = timezone.localdate()
    sheets = []
    for e in _picked(request, pk):
        papers = list(e.papers.all())
        items = file_checklist(e, s.needs, papers, today)
        listed = {k for i in items for k in i["kinds"]}
        others = [p for p in papers if p.kind not in listed]
        sheets.append({"e": e, "items": items, "others": others})
    return render(request, "staff/print_file.html", {"sheets": sheets, "today": today})


CARD_COLOURS = {"production": "orange", "shop": "teal", "admin": "burgundy", "delivery": "warm",
                "security": "burgundy", "cleaning": "teal"}


@need("staff")
def print_cards(request, pk=None):
    people = _picked(request, pk)
    colour = request.GET.get("colour", "dept")
    for e in people:
        e.card = colour if colour in ("orange", "teal", "burgundy", "warm") else CARD_COLOURS.get(e.department, "orange")
    pages = [people[i:i + 8] for i in range(0, len(people), 8)] or [[]]
    return render(request, "staff/print_cards.html", {
        "pages": pages, "people": people, "colour": colour, "depts": DEPARTMENTS, "card_colours": CARD_COLOURS,
        "pk": pk, "ids": request.GET.get("ids", "")})
