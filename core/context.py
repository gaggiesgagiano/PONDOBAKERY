import os
from django.utils import timezone

from .access import OLD_LABELS, PRESETS, rights
from .areas import area_info, area_of, menu
from .look import resolve
from .models import CompanySettings, Shop


def shop(request):
    cs = CompanySettings.get()
    look = resolve(cs, getattr(request, "user", None))
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"look": look, "company": cs}

    can = rights(request)
    try:
        from .daily_backup import status
        _st = status(cs)
        from django.conf import settings as dj
        if getattr(dj, "ONLINE", False):   # online: a manager downloads a copy once a week
            stale = can.backup and (cs.last_flash_backup is None or (timezone.now() - cs.last_flash_backup).days >= 7)
        else:
            stale = can.backup and bool(_st["today_pending"] or _st["locked_day"] or cs.last_flash_backup is None)
    except Exception:  # noqa: BLE001
        stale = False
    if can.owner:
        role = "Manager"
    else:
        key = getattr(can.acc, "role", "")
        role = PRESETS[key]["label"] if key in PRESETS else OLD_LABELS.get(key, "Custom rights")
    match = getattr(request, "resolver_match", None)
    area_key = area_of(match)
    if area_key == "recipes" and getattr(match, "url_name", "") == "recipes" and (
            request.GET.get("gp_min") or request.GET.get("gp_max") or request.GET.get("show") == "low"):
        area_key = "gpcheck"  # GP check is the recipe list filtered on GP – light up its own menu item
    return {
        "demo": os.environ.get("PONDO_DEMO") == "1",
        "area": area_info(area_key),
        "menu": menu(can, area_key),
        "company": cs,
        "current_shop": Shop.objects.filter(active=True).first(),
        "backup_reminder": stale,
        "user_role": role,
        "look": look,
        "can": can,
        "nav": request.resolver_match.namespace if request.resolver_match else "",
    }
