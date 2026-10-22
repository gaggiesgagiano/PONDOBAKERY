"""Daily backup rule: after the last cash-up of the day a flash-drive backup must be made.
If the last trading day (the last day with cash-ups) was not backed up, Pondo is locked the next day until it is done."""
import datetime

from django.db.models import Max
from django.utils import timezone

START = datetime.date(2099, 1, 1)   # PAUSED while the shop is not open yet – set to the opening day when trading starts


def _latest_change(day):
    from sales.models import CashUp
    agg = CashUp.objects.filter(date=day).aggregate(c=Max("created_at"), s=Max("signed_off_at"))
    times = [t for t in (agg["c"], agg["s"]) if t]
    return max(times) if times else None


def backed_up(day, cs):
    latest = _latest_change(day)
    return latest is None or (cs.last_flash_backup is not None and cs.last_flash_backup >= latest)


def status(cs=None, today=None):
    """{'locked_day': date or None – a past trading day without backup (Pondo is locked),
        'today_pending': True when today's cash-ups are not backed up yet}"""
    from sales.models import CashUp
    from .models import CompanySettings
    cs = cs or CompanySettings.get()
    today = today or timezone.localdate()
    prev = (CashUp.objects.filter(date__lt=today, date__gte=START).order_by("-date")
            .values_list("date", flat=True).first())
    locked = prev if prev and not backed_up(prev, cs) and cs.backup_waived_on != today else None
    today_pending = (today >= START and CashUp.objects.filter(date=today).exists() and not backed_up(today, cs))
    return {"locked_day": locked, "today_pending": today_pending}
