from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import redirect

OPEN_PATHS = ("/login/", "/static/", "/setup/", "/brand/font/")


class LoginRequiredMiddleware:
    """Every screen needs a login, except the login page itself.
    On the very first start (no users yet) everyone is sent to the set-up page."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._has_users = False

    def __call__(self, request):
        if not self._has_users:
            self._has_users = User.objects.exists()
            if not self._has_users and not request.path.startswith(("/setup/", "/static/")):
                return redirect("/setup/")
        if not request.user.is_authenticated and not request.path.startswith(OPEN_PATHS):
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")
        return self.get_response(request)


LOCK_OPEN = ("/login/", "/logout/", "/static/", "/setup/", "/brand/font/", "/backup", "/manual/", "/password/", "/media/")


class DailyBackupLockMiddleware:
    """Yesterday's (last trading day's) cash-ups were not backed up to the flash drive:
    nobody can start working until the backup is made (Back up now stays open)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "ONLINE", False):
            return self.get_response(request)          # online: the server backs up by itself every night
        if request.user.is_authenticated and not request.path.startswith(LOCK_OPEN):
            try:
                from .daily_backup import status
                st = status()
            except Exception:  # noqa: BLE001 – never lock people out because of an error in the check itself
                st = {"locked_day": None}
            if st["locked_day"]:
                return redirect("core:backup_needed")
        return self.get_response(request)


class PrivateFontMiddleware:
    """Online: the paid brand font (Retro Star) is only sent to people who are logged in –
    never to strangers on the internet (the log-in page then uses the free fonts)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (getattr(settings, "ONLINE", False) and not request.user.is_authenticated
                and (request.path.startswith("/static/fonts/retro-star") or request.path.startswith("/brand/font/"))):
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound()
        return self.get_response(request)
