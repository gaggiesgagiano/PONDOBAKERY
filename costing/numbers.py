"""Recipe numbers: the series 201001–201999 (999 numbers). Shows which numbers are still free."""
FIRST, LAST = 201001, 201999


def used_numbers():
    from .models import Recipe

    return set(Recipe.objects.values_list("number", flat=True))  # archived recipes keep their number


def free_runs(used=None):
    """Free numbers between the first and the highest used number, as runs: [(start, end), ...]."""
    used = used if used is not None else used_numbers()
    in_series = sorted(n for n in used if FIRST <= n <= LAST)
    if not in_series:
        return []
    runs, start = [], None
    for n in range(FIRST, in_series[-1] + 1):
        if n not in used:
            start = n if start is None else start
        elif start is not None:
            runs.append((start, n - 1)); start = None
    return runs


def suggestions(limit=12):
    """Free numbers to offer for a new recipe: the gaps first, then the next numbers after the highest."""
    used = used_numbers()
    out = []
    for a, b in free_runs(used):
        for n in range(a, b + 1):
            out.append(n)
            if len(out) >= limit - 1:
                break
        if len(out) >= limit - 1:
            break
    nxt = max([n for n in used if FIRST <= n <= LAST], default=FIRST - 1) + 1
    if nxt <= LAST and nxt not in out:
        out.append(nxt)
    return out


def stats():
    used = used_numbers()
    in_series = [n for n in used if FIRST <= n <= LAST]
    gaps = sum(b - a + 1 for a, b in free_runs(used))
    total = LAST - FIRST + 1
    return {"first": FIRST, "last": LAST, "total": total, "used": len(in_series), "free": total - len(in_series),
            "gaps": gaps, "highest": max(in_series, default=None)}
