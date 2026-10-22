"""Writes the login register: every log-in, log-out and wrong password, with the computer or phone it came from."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver


def _ip(request):
    if request is None:
        return ""
    return (request.META.get("REMOTE_ADDR") or "")[:60]


def device_name(ua):
    """'Chrome on Windows', 'Android phone', 'iPhone' … from the browser's user-agent text."""
    ua = ua or ""
    low = ua.lower()
    if "iphone" in low:
        os_ = "iPhone"
    elif "ipad" in low:
        os_ = "iPad"
    elif "android" in low:
        os_ = "Android phone" if "mobile" in low else "Android tablet"
    elif "windows" in low:
        os_ = "Windows"
    elif "mac os" in low or "macintosh" in low:
        os_ = "Mac"
    elif "linux" in low:
        os_ = "Linux"
    else:
        os_ = ""
    if "edg/" in low:
        br = "Edge"
    elif "opr/" in low or "opera" in low:
        br = "Opera"
    elif "chrome/" in low and "chromium" not in low:
        br = "Chrome"
    elif "firefox/" in low:
        br = "Firefox"
    elif "safari/" in low:
        br = "Safari"
    else:
        br = ""
    if br and os_:
        return f"{br} on {os_}"
    return br or os_ or (ua[:60] if ua else "")


def _record(request, event, user=None, username=""):
    from .models import LoginRecord
    try:
        ua = request.META.get("HTTP_USER_AGENT", "") if request is not None else ""
        LoginRecord.objects.create(user=user, username=(username or (user.get_username() if user else ""))[:150],
                                   event=event, ip=_ip(request), device=device_name(ua)[:120])
    except Exception:  # noqa: BLE001 – the register must never stop anybody logging in
        pass


@receiver(user_logged_in)
def _in(sender, request, user, **kw):
    _record(request, "in", user)


@receiver(user_logged_out)
def _out(sender, request, user, **kw):
    _record(request, "out", user)


@receiver(user_login_failed)
def _failed(sender, credentials, request=None, **kw):
    _record(request, "failed", None, (credentials or {}).get("username", ""))
