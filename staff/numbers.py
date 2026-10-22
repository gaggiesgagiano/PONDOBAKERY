"""Staff numbers. Normally the year the person started + a running number for that year: 26001, 26002 …
(someone starting in 2027 gets 27001). Plain numbers, so the fingerprint machine can use the same number.
A number is never given out twice, also not when someone has left."""
import datetime
import re

from .models import Employee, PayrollSettings


def lead(s, start=None):
    """What comes before the running number: the 2-digit year started (26) or the letters (PB-)."""
    if s.staff_no_style == PayrollSettings.LETTERS:
        return s.staff_no_prefix or ""
    return f"{(start or datetime.date.today()).year % 100:02d}"


def fmt(lead_text, digits, n):
    return f"{lead_text or ''}{n:0{max(1, digits or 1)}d}"


def _pattern(lead_text):
    return re.compile(r"^\s*" + re.escape((lead_text or "").strip()) + r"\s*(\d+)\s*$", re.I)


def highest(lead_text, digits=3):
    pat, top = _pattern(lead_text), 0
    for code in Employee.objects.exclude(code="").values_list("code", flat=True):
        m = pat.match(code)
        # in the year style only numbers of the right length count (26001, not an old 001)
        if m and (not lead_text.isdigit() or len(m.group(1)) >= digits):
            top = max(top, int(m.group(1)))
    return top


def next_number(s=None, start=None):
    s = s or PayrollSettings.get()
    ld = lead(s, start)
    return fmt(ld, s.staff_no_digits, highest(ld, s.staff_no_digits) + 1)


def number_everyone():
    """Give a number to everybody still working here who has none: longest-serving first, then in the order added."""
    s = PayrollSettings.get()
    done = []
    for e in Employee.objects.filter(active=True, code="").order_by("start_date", "pk"):
        e.code = next_number(s, e.start_date)
        e.save(update_fields=["code", "updated_at"])
        done.append(e)
    return done


def taken_by(code, exclude_pk=None):
    code = (code or "").strip()
    if not code:
        return None
    qs = Employee.objects.filter(code__iexact=code)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()
