"""Staff cards with a photo and a barcode – for every staff member.

Scan to log in, and scan to approve on the till (instead of typing a password). Later the same card opens the staff
account. A card holds a random code – never the password. 'New card' replaces a lost card and the old one stops
working straight away; a staff member who has left can't use their card any more."""
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from . import barcode128
from .access import PRESETS
from .models import StaffCard, log_change

owner_only = user_passes_test(lambda u: u.is_superuser)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code():
    while True:
        code = "PB" + "".join(secrets.choice(ALPHABET) for _ in range(10))
        if not StaffCard.objects.filter(code=code).exists():
            return code


def clean_code(raw):
    return "".join(ch for ch in (raw or "").upper() if ch.isalnum())[:20]


def card_from_code(raw):
    """The working card for a scanned code (None when unknown, stopped, or the person has left)."""
    code = clean_code(raw)
    if len(code) < 8:
        return None
    card = StaffCard.objects.filter(code=code, active=True).select_related("user", "employee").first()
    if not card or (card.employee_id and not card.employee.active):
        return None
    return card


def user_from_card(raw):
    card = card_from_code(raw)
    return card.user if card and card.user_id and card.user.is_active else None


def approver(request):
    """The person approving on the till: from a scanned card, or from username + password."""
    from django.contrib.auth import authenticate
    if (request.POST.get("card") or "").strip():
        return user_from_card(request.POST.get("card"))
    return authenticate(request, username=(request.POST.get("by") or "").strip(), password=request.POST.get("pw") or "")


def role_label(u):
    if u is None:
        return ""
    if u.is_superuser:
        return "Manager"
    acc = getattr(u, "access", None)
    return PRESETS.get(acc.role, {}).get("label", "Staff") if acc and acc.role else "Staff"


def _user_name(u):
    return f"{u.first_name} {u.last_name}".strip() or u.username


def _employees():
    from staff.models import Employee
    return [e for e in Employee.objects.filter(active=True) if not e.is_open]


@owner_only
def cards_list(request):
    User = get_user_model()
    cards = {c.employee_id: c for c in StaffCard.objects.filter(employee__isnull=False).select_related("user")}
    staff = [{"e": e, "card": cards.get(e.pk)} for e in _employees()]
    linked = {c.user_id for c in cards.values() if c.user_id}
    users = list(User.objects.filter(is_active=True).select_related("access").order_by("first_name", "username"))
    login_only = [{"u": u, "card": StaffCard.objects.filter(user=u, employee__isnull=True).first(), "role": role_label(u)}
                  for u in users if u.pk not in linked]
    choices = [{"u": u, "label": f"{_user_name(u)} ({u.username}) – {role_label(u)}"} for u in users]
    return render(request, "core/cards.html", {"staff": staff, "login_only": login_only, "choices": choices,
                                               "linked": linked})


def _issue(card):
    card.code, card.issued_at, card.active = new_code(), timezone.now(), True
    card.save()


@owner_only
@require_POST
def card_new(request, kind, pk):
    """kind 'staff' = a staff member (Employee), 'login' = a login with no staff record (e.g. the owner)."""
    if kind not in ("staff", "login"):
        from django.http import Http404
        raise Http404
    if kind == "staff":
        from staff.models import Employee
        e = get_object_or_404(Employee, pk=pk, active=True)
        card = StaffCard.objects.filter(employee=e).first()
        who = e.name
    else:
        u = get_object_or_404(get_user_model(), pk=pk)
        card = StaffCard.objects.filter(user=u).first()
        who = _user_name(u)
    old = card is not None and bool(card.code)
    if card is None:
        card = StaffCard(employee=e) if kind == "staff" else StaffCard(user=u)
    _issue(card)
    log_change(request.user, "Staff cards", who, "new card" if old else "card made", "the old card no longer works" if old else "")
    messages.success(request, f"New card for {who}." + (" The old card no longer works." if old else "") + " Print it now.")
    return redirect(f"/settings/cards/print/?ids={card.pk}")


@owner_only
@require_POST
def card_all(request):
    """Make a card for every staff member who doesn't have one yet, then print all of them."""
    n = 0
    for e in _employees():
        if not StaffCard.objects.filter(employee=e).exists():
            _issue(StaffCard(employee=e))
            n += 1
    if n:
        log_change(request.user, "Staff cards", f"{n} staff", "cards made")
    messages.success(request, f"{n} new card{'s' if n != 1 else ''} made." if n else "Everybody already has a card.")
    return redirect("/settings/cards/print/")


@owner_only
@require_POST
def card_link(request, pk):
    """Join a staff member's card to their Pondo login, so the card logs in and (for supervisors) approves."""
    from staff.models import Employee
    e = get_object_or_404(Employee, pk=pk)
    uid = request.POST.get("user") or ""
    with transaction.atomic():
        card = StaffCard.objects.filter(employee=e).first()
        if card is None:
            card = StaffCard(employee=e)
            _issue(card)
        if uid:
            u = get_object_or_404(get_user_model(), pk=uid)
            other = StaffCard.objects.filter(user=u).exclude(pk=card.pk).first()
            if other and other.employee_id:
                messages.error(request, f"That login is already on {other.employee.name}'s card.")
                return redirect("core:cards")
            if other:              # a login-only card: the staff card takes over (the old login card stops)
                other.delete()
            card.user = u
            msg = f"{e.name}'s card now logs in as {u.username}."
        else:
            card.user = None
            msg = f"{e.name}'s card no longer logs in."
        card.save()
    log_change(request.user, "Staff cards", e.name, "login on card", card.user.username if card.user else "none")
    messages.success(request, msg)
    return redirect("core:cards")


@owner_only
@require_POST
def card_stop(request, pk):
    card = get_object_or_404(StaffCard, pk=pk)
    card.active = False
    card.save(update_fields=["active"])
    who = card.employee.name if card.employee_id else _user_name(card.user)
    log_change(request.user, "Staff cards", who, "card stopped")
    messages.success(request, f"{who}'s card no longer works.")
    return redirect("core:cards")


def _colour(e):
    from staff.files import CARD_COLOURS
    return CARD_COLOURS.get(e.department, "orange") if e else "burgundy"


def card_item(c):
    e, u = c.employee, c.user
    if e:
        name, job, no = e.name, e.job_title or e.get_department_display(), e.code
    else:
        name, job, no = _user_name(u), role_label(u), ""
    return {"c": c, "e": e, "u": u, "name": name, "job": job, "no": no, "dept": e.get_department_display() if e else "",
            "colour": _colour(e),
            "approves": bool(u and (u.is_superuser or role_label(u) in ("Supervisor", "Assistant Manager", "Admin"))),
            "svg": mark_safe(barcode128.svg(c.code, module=2, height=56, quiet=10))}


@owner_only
def cards_print(request):
    ids = [int(x) for x in request.GET.get("ids", "").split(",") if x.strip().isdigit()]
    cards = StaffCard.objects.filter(active=True).select_related("user", "user__access", "employee")
    if ids:
        cards = cards.filter(pk__in=ids)
    cards = [c for c in cards if not (c.employee_id and not c.employee.active)]
    cards.sort(key=lambda c: (c.employee is None, (c.employee.code if c.employee else "") or "~", card_item(c)["name"]))
    items = [card_item(c) for c in cards]
    pages = [items[i:i + 8] for i in range(0, len(items), 8)] or [[]]
    return render(request, "core/cards_print.html", {"pages": pages})


@require_POST
def card_login(request):
    from .login_log import _record
    u = user_from_card(request.POST.get("card"))
    if not u:
        _record(request, "failed", None, "staff card " + clean_code(request.POST.get("card"))[-4:])
        card = card_from_code(request.POST.get("card"))
        return redirect("/login/?card=" + ("nologin" if card else "bad"))
    login(request, u, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(0)
    nxt = request.POST.get("next") or "/"
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
