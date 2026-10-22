"""SOP exam papers and memos – only for the owner, and only after typing the login password again.

The PDFs live in data/private/exams (never in static or media), are served by this view only, and every
opening is written in the change log."""
import re
import time
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import log_change

UNLOCK_MINUTES = 10
MAX_WRONG = 5
KEY, WRONG = "exams_unlocked_at", "exams_wrong"


def exam_dir():
    d = Path(settings.DATA_DIR) / "private" / "exams"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _owner(request):
    if not request.user.is_superuser:
        raise Http404  # other users don't even see that the page exists


def _unlocked(request):
    t = request.session.get(KEY)
    return bool(t) and time.time() - t < UNLOCK_MINUTES * 60


def _files():
    papers, memos = [], []
    for f in sorted(exam_dir().glob("*.pdf"), key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.name)]):
        (memos if "memo" in f.name.lower() else papers).append(f.name)
    return papers, memos


@login_required
def exam_list(request):
    _owner(request)
    if request.method == "POST" and "password" in request.POST:
        wrong = request.session.get(WRONG, 0)
        if wrong >= MAX_WRONG:
            messages.error(request, "Too many wrong passwords. Log out and in again to try once more.")
        elif request.user.check_password(request.POST.get("password", "")):
            request.session[KEY], request.session[WRONG] = time.time(), 0
            log_change(request.user, "SOP exams", "SOP exams", "opened")
        else:
            request.session[WRONG] = wrong + 1
            log_change(request.user, "SOP exams", "SOP exams", "wrong password")
            messages.error(request, "Wrong password.")
        return redirect("core:exams")
    if not _unlocked(request):
        resp = render(request, "core/exams.html", {"locked": True, "minutes": UNLOCK_MINUTES})
    else:
        papers, memos = _files()
        left = int(UNLOCK_MINUTES - (time.time() - request.session[KEY]) / 60) + 1
        resp = render(request, "core/exams.html", {"locked": False, "papers": papers, "memos": memos, "left": left,
                                                   "folder": exam_dir()})
    resp["Cache-Control"] = "no-store"
    return resp


@login_required
def exam_file(request, name):
    _owner(request)
    if not _unlocked(request):
        return redirect("core:exams")
    papers, memos = _files()
    if name not in papers + memos:
        raise Http404
    log_change(request.user, "SOP exams", name, "printed / opened")
    resp = FileResponse(open(exam_dir() / name, "rb"), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{name}"'
    resp["Cache-Control"] = "no-store"
    return resp


@login_required
@require_POST
def exam_lock(request):
    _owner(request)
    request.session.pop(KEY, None)
    return redirect("core:exams")
