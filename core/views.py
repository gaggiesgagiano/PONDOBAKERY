from django.contrib.auth import views as auth_views
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from costing import calc
from costing.models import Ingredient, Recipe

from . import backup
from .forms import CompanySettingsForm, NewUserForm, ShopForm
from .access import AREA_GROUPS, AREAS, DEFAULT_ROLE, LEVELS, PRESETS, need, rights
from .models import Access, ChangeLog, CompanySettings, Shop, log_change

owner_only = user_passes_test(lambda u: u.is_superuser)


def _sales_figures(request):
    """Sales tiles for people with access to Sales & Cash-Up."""
    if not rights(request).sales_view:
        return {}
    import datetime

    from django.db.models import Sum
    from django.utils import timezone

    from sales.models import CashUp
    today = timezone.localdate()
    month = today.replace(day=1)
    last_start = (month - datetime.timedelta(days=1)).replace(day=1)
    same_day_last = min(today.day, (month - datetime.timedelta(days=1)).day)
    qs = CashUp.objects
    return {
        "sales_today": qs.filter(date=today).aggregate(s=Sum("total_sales"))["s"],
        "sales_month": qs.filter(date__gte=month, date__lte=today).aggregate(s=Sum("total_sales"))["s"],
        "sales_last": qs.filter(date__gte=last_start, date__lte=last_start.replace(day=same_day_last)).aggregate(s=Sum("total_sales"))["s"],
        "cu_waiting": qs.filter(signed_off_by__isnull=True).count(),
        "cu_short": qs.filter(date__gte=month, total_variance__lt=0).aggregate(s=Sum("total_variance"))["s"],
        "show_sales": True,
    }


def _jobs(request, d):
    from .jobs import todays_jobs

    r = rights(request)
    cs = CompanySettings.get()
    due = r.backup and (cs.last_flash_backup is None or (timezone.now() - cs.last_flash_backup).days >= 7)
    return todays_jobs(r, d, due, user=request.user)


def dashboard(request):
    cs = CompanySettings.get()
    if not rights(request).costs:
        return render(request, "core/dashboard.html", {"simple": True, "jobs": _jobs(request, timezone.localdate()),
                                                       **_sales_figures(request)})
    import datetime

    from .daily import dashboard_data

    today = timezone.localdate()
    try:
        d = datetime.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        d = today
    ctx = dashboard_data(d)
    costs = calc.Calculator().preload()
    low = []
    for r in Recipe.objects.filter(active=True, sell_price__isnull=False).select_related("category"):
        gp = costs.gp(r)
        if gp is not None and gp < cs.gp_low:
            low.append((r, gp))
    low.sort(key=lambda x: x[1])
    ctx.update({
        "today": today, "is_today": d == today, "prev_day": d - datetime.timedelta(days=1),
        "next_day": d + datetime.timedelta(days=1) if d < today else None,
        "low_gp": low[:8], "n_low": len(low),
        "unpriced": Ingredient.objects.filter(active=True, kind=Ingredient.BOUGHT, pack_price__isnull=True).count(),
        "no_price_products": Recipe.objects.filter(active=True, is_subrecipe=False, sell_price__isnull=True).count(),
        "jobs": _jobs(request, d),
    })
    return render(request, "core/dashboard.html", ctx)


@owner_only
def settings_view(request):
    cs = CompanySettings.get()
    shop = Shop.objects.first() or Shop.objects.create()
    if request.method == "POST":
        f1 = CompanySettingsForm(request.POST, instance=cs, prefix="c")
        f2 = ShopForm(request.POST, instance=shop, prefix="s")
        if f1.is_valid() and f2.is_valid():
            old_rate = CompanySettings.objects.filter(pk=cs.pk).values_list("zwg_rate", flat=True).first()
            cs = f1.save(commit=False)
            if cs.zwg_rate != old_rate:
                cs.zwg_rate_at = timezone.now()
                log_change(request.user, "Settings", "ZWG rate", "changed",
                           f"{old_rate if old_rate is not None else '–'} → {cs.zwg_rate if cs.zwg_rate is not None else '–'} ZWG per US$1")
            cs.save()
            f2.save()
            log_change(request.user, "Settings", "Business settings", "changed")
            messages.success(request, "Settings saved.")
            return redirect("core:settings")
    else:
        f1 = CompanySettingsForm(instance=cs, prefix="c")
        f2 = ShopForm(instance=shop, prefix="s")
    return render(request, "core/settings.html", {"f1": f1, "f2": f2})


def dashboard_print(request):
    """The daily dashboard on one A4 page."""
    import datetime

    from django.utils import timezone

    from .access import rights as _rights
    from .daily import dashboard_data

    if not _rights(request).costs:
        return redirect("core:dashboard")
    try:
        d = datetime.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        d = timezone.localdate()
    return render(request, "print/dashboard.html", dashboard_data(d))


def help_view(request):
    return render(request, "core/help.html")


@owner_only
def targets_view(request):
    """Costs & targets – the Excel 'Staff & Costs' sheet."""
    from .forms import OverheadFormSet, TargetsForm
    from .models import Overhead
    from .targets import Targets

    cs = CompanySettings.get()
    form = TargetsForm(request.POST or None, instance=cs)
    fs = OverheadFormSet(request.POST or None, queryset=Overhead.objects.all(), prefix="o")
    if request.method == "POST" and form.is_valid() and fs.is_valid():
        form.save()
        objs = fs.save(commit=False)
        for o in fs.deleted_objects:
            o.delete()
        for n, o in enumerate(objs):
            if not o.sort_order:
                o.sort_order = Overhead.objects.count() + n + 1
            o.save()
        log_change(request.user, "Settings", "Costs & targets", "changed")
        messages.success(request, "Costs & targets saved. The dashboard uses them straight away.")
        return redirect("core:targets")
    return render(request, "core/targets.html", {"form": form, "fs": fs, "t": Targets()})


@owner_only
def users_view(request):
    form = NewUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = User.objects.create_user(form.cleaned_data["username"], password=form.cleaned_data["password"],
                                     first_name=form.cleaned_data["first_name"])
        role = form.cleaned_data["role"]
        Access.from_preset(u, role if role in PRESETS else DEFAULT_ROLE)
        log_change(request.user, "Users", u.username, "added", f"role: {role}")
        messages.success(request, f"User '{u.username}' added. Check or change their rights below.")
        return redirect("core:user_rights", pk=u.pk)
    users = []
    for u in User.objects.order_by("-is_superuser", "username"):
        acc = None if u.is_superuser else (Access.objects.filter(user=u).first() or Access.from_preset(u, DEFAULT_ROLE))
        users.append((u, acc))
    return render(request, "core/users.html", {"form": form, "users": users, "presets": PRESETS})


@owner_only
def user_rights(request, pk):
    u = get_object_or_404(User, pk=pk, is_superuser=False)
    acc = Access.objects.filter(user=u).first() or Access.from_preset(u, DEFAULT_ROLE)
    if request.method == "POST":
        preset = request.POST.get("preset")
        if preset in PRESETS:
            Access.from_preset(u, preset)
            messages.success(request, f"{u.username} now has the {PRESETS[preset]['label']} rights. Adjust below if needed.")
            log_change(request.user, "Users", u.username, "rights changed", f"role: {preset}")
            return redirect("core:user_rights", pk=u.pk)
        changes = []
        for key, label, _, _ in AREAS:
            # two ticks per area: "can see" and "can change" (change includes see)
            v = 2 if request.POST.get(key + "_change") else 1 if request.POST.get(key + "_see") else 0
            if getattr(acc, key) != v:
                changes.append(f"{label}: {dict(LEVELS)[v]}")
            setattr(acc, key, v)
        for key in ("see_costs", "backup"):
            v = request.POST.get(key) == "on"
            if getattr(acc, key) != v:
                changes.append(f"{key.replace('_', ' ')}: {'yes' if v else 'no'}")
            setattr(acc, key, v)
        acc.role = "custom" if changes else acc.role
        acc.save()
        log_change(request.user, "Users", u.username, "rights changed", "; ".join(changes))
        messages.success(request, f"Rights for {u.username} saved.")
        return redirect("core:users")
    info = {k: (label, help_) for k, label, help_, _ in AREAS}
    groups = [(title, [(k, info[k][0], info[k][1], getattr(acc, k)) for k in keys]) for title, keys in AREA_GROUPS]
    return render(request, "core/user_rights.html", {"person": u, "acc": acc, "groups": groups, "presets": PRESETS})


@owner_only
@require_POST
def user_toggle(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u == request.user:
        messages.error(request, "You cannot switch off your own login.")
    else:
        u.is_active = not u.is_active
        u.save()
        log_change(request.user, "Users", u.username, "enabled" if u.is_active else "disabled")
        messages.success(request, f"{u.username} is now {'active' if u.is_active else 'switched off'}.")
    return redirect("core:users")


@owner_only
@require_POST
def user_password(request, pk):
    u = get_object_or_404(User, pk=pk)
    pw = request.POST.get("password", "")
    if len(pw) < 8:
        messages.error(request, "The new password must be at least 8 characters.")
    else:
        u.set_password(pw)
        u.save()
        log_change(request.user, "Users", u.username, "password reset")
        messages.success(request, f"Password for {u.username} changed.")
    return redirect("core:users")


@need(backup=True)
def backup_view(request):
    cs = CompanySettings.get()
    from django.conf import settings as dj
    if getattr(dj, "ONLINE", False):
        return _backup_online(request, cs)
    drives = backup.flash_drives()
    if request.method == "POST":
        drive = request.POST.get("drive")
        if drive not in drives:
            messages.error(request, "That flash drive is no longer plugged in. Plug it in and try again.")
        else:
            try:
                dest = backup.backup_to_drive(drive)
            except OSError as e:
                messages.error(request, f"Could not write to the flash drive: {e}")
            else:
                cs.last_flash_backup = timezone.now()
                cs.last_flash_backup_to = str(dest)
                cs.save()
                log_change(request.user, "Backup", str(dest), "flash drive backup")
                messages.success(request, f"Backup saved on the flash drive: {dest}")
                from .daily_backup import status
                if request.POST.get("next") == "start" and not status(cs)["locked_day"]:
                    messages.success(request, "Pondo is open again – have a good day.")
                    return redirect("core:dashboard")
            return redirect("core:backup")
    local = sorted(backup.settings.BACKUP_DIR.glob("pondo_*.sqlite3"), reverse=True)[:10]
    from .daily_backup import status
    return render(request, "core/backup.html", {"drives": drives, "local": local, "daily": status(cs),
                                                "start": request.GET.get("start") == "1"})


def _backup_online(request, cs):
    """Online: the server makes a backup every night; a manager downloads a copy once a week to keep in the office."""
    from django.http import FileResponse, Http404
    nightly = backup.nightly_zips()
    want = request.GET.get("file")
    if request.method == "POST" or want:
        if want:
            f = next((z for z in nightly if z.name == want), None)
            if f is None:
                raise Http404
        else:
            f = backup.make_zip(reason="download")
        cs.last_flash_backup = timezone.now()
        cs.last_flash_backup_to = f"downloaded by {request.user.username}: {f.name}"
        cs.save(update_fields=["last_flash_backup", "last_flash_backup_to"])
        log_change(request.user, "Backup", f.name, "backup downloaded")
        return FileResponse(open(f, "rb"), as_attachment=True, filename=f.name)
    return render(request, "core/backup_online.html", {"nightly": nightly[:14]})


def backup_needed(request):
    """The lock screen: the last trading day's cash-ups were not backed up – nobody starts until it is done."""
    from .access import rights
    from .daily_backup import status
    st = status()
    if not st["locked_day"]:
        return redirect("core:dashboard")
    return render(request, "core/backup_needed.html", {"day": st["locked_day"], "can_backup": rights(request).backup,
                                                       "is_owner": rights(request).owner})


def backup_waive(request):
    """Only the Manager: open Pondo today without yesterday's backup (e.g. flash drive lost) – with a reason."""
    from .access import rights
    if request.method != "POST" or not rights(request).owner:
        return redirect("core:backup_needed")
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < 5:
        messages.error(request, "Write the reason why the backup can't be made.")
        return redirect("core:backup_needed")
    cs = CompanySettings.get()
    cs.backup_waived_on = timezone.localdate()
    cs.save(update_fields=["backup_waived_on"])
    log_change(request.user, "Backup", "Daily backup", "skipped for today", reason)
    messages.warning(request, "Pondo is open for today without yesterday's backup. Make a backup as soon as you can.")
    return redirect("core:dashboard")


@owner_only
def changelog_view(request):
    """Change history – and the login register (?tab=logins): who logged in, when and from where."""
    from django.contrib.auth import get_user_model
    from .models import LoginRecord
    tab = "logins" if request.GET.get("tab") == "logins" else "changes"
    who = request.GET.get("who", "")
    users = get_user_model().objects.order_by("username")
    if tab == "logins":
        qs = LoginRecord.objects.select_related("user")
        if who:
            qs = qs.filter(username=who)
        if request.GET.get("failed") == "1":
            qs = qs.filter(event=LoginRecord.FAILED)
        rows = qs[:500]
    else:
        qs = ChangeLog.objects.select_related("user")
        if who:
            qs = qs.filter(user__username=who)
        rows = qs[:300]
    return render(request, "core/changelog.html", {"rows": rows, "tab": tab, "who": who, "users": users,
                                                   "failed": request.GET.get("failed") == "1"})



class LoginView(auth_views.LoginView):
    """The login page. 'Keep me logged in' lets this laptop open the program straight away for 30 days."""

    template_name = "core/login.html"
    REMEMBER_DAYS = 30
    MAX_WRONG, BLOCK_MINUTES = 5, 15
    locked = False

    def post(self, request, *args, **kwargs):
        """5 wrong passwords for one name within 15 minutes: that name is blocked for 15 minutes (stops guessing)."""
        from datetime import timedelta
        from .models import LoginRecord
        name = (request.POST.get("username") or "").strip()
        since = timezone.now() - timedelta(minutes=self.BLOCK_MINUTES)
        if name and LoginRecord.objects.filter(event=LoginRecord.FAILED, username__iexact=name, when__gte=since).count() >= self.MAX_WRONG:
            self.locked = True
            form = self.get_form()
            form.is_valid = lambda: False
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["locked"] = self.locked
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember"):
            self.request.session.set_expiry(self.REMEMBER_DAYS * 24 * 3600)
        else:
            self.request.session.set_expiry(0)  # ends when the browser closes (or after 12 hours)
        return response
