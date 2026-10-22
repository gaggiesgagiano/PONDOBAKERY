from decimal import Decimal

from django import template

register = template.Library()


def _d(v):
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


@register.filter
def money(v, places=2):
    d = _d(v)
    if d is None:
        return "–"
    places = int(places)
    s = f"{abs(d):,.{places}f}"
    return f"-${s}" if d < 0 else f"${s}"


@register.filter
def num(v, places=3):
    """Quantity: up to N decimals, trailing zeros removed."""
    d = _d(v)
    if d is None:
        return "–"
    s = f"{d:,.{int(places)}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


@register.filter
def pct(v, places=1):
    d = _d(v)
    if d is None:
        return "–"
    return f"{d * 100:.{int(places)}f}%"


@register.filter
def gpclass(v, company=None):
    d = _d(v)
    if d is None:
        return "gp-none"
    low = company.gp_low if company else Decimal("0.45")
    target = company.target_gp if company else Decimal("0.60")
    if d < low:
        return "gp-low gp-red"  # below the red line (Settings: "Show GP in red below %")
    if d < target:
        return "gp-mid"
    return "gp-ok"


@register.filter
def widthpct(v):
    d = _d(v)
    if d is None:
        return "0"
    return f"{max(0, min(100, float(d) * 100)):.1f}"


@register.filter
def sub(a, b):
    a, b = _d(a), _d(b)
    return None if a is None or b is None else a - b


@register.filter
def mul(a, b):
    a, b = _d(a), _d(b)
    return None if a is None or b is None else a * b


@register.filter
def sign(v):
    """'neg' for amounts below zero (shown red), 'pos' otherwise."""
    d = _d(v)
    return "" if d is None else ("neg" if d < 0 else "pos")


@register.filter
def get_item(d, key):
    """{{ dict|get_item:key }}"""
    try:
        return d.get(key, "")
    except AttributeError:
        return ""


BRAND_LINES = [
    "Let's make the everyday treat feel like a small win.",
    "Good food, fair value and a little moment of pleasure in the day.",
    "Quality – fresh, satisfying and well crafted, every time.",
    "Keep it simple: easy to choose, easy to grab, easy to enjoy.",
    "Consistency is what makes people come back.",
    "Bring the joy – small moments that make people smile.",
    "Pondo yako chete!",
]


@register.simple_tag
def hello():
    """('Good morning', a brand line that changes every day)."""
    from django.utils import timezone

    now = timezone.localtime()
    part = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
    return {"part": part, "line": BRAND_LINES[now.timetuple().tm_yday % len(BRAND_LINES)]}
