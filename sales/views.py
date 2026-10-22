import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need, rights
from core.models import log_change
from costing.calc import Calculator
from costing.models import Recipe

from .forms import (CashUpHeaderForm, ExpenseCategoryForm, ExpenseForm, NewCashUpForm, NewDaySalesForm,
                    PaymentMethodForm, PayoutFormSet, SaleLineFormSet, TakingsForm)
from .models import CashUp, CashUpLine, DaySales, Expense, ExpenseCategory, PaymentMethod, SaleLine
from .report import month_bounds, month_report, parse_month

Z = Decimal("0")


def _can_manage(request):
    r = rights(request)
    return r.owner or r.costs


def _locked(request, obj):
    return bool(obj.signed_off_by) and not rights(request).owner


# ======================================================================= cash-up
@need("sales")
def cashup_list(request):
    cus = CashUp.objects.select_related("created_by", "signed_off_by")[:150]
    return render(request, "sales/cashup_list.html", {"cus": cus, "form": NewCashUpForm(),
                                                      "waiting": CashUp.objects.filter(signed_off_by__isnull=True).count()})


@need("sales", EDIT)
@require_POST
def cashup_new(request):
    form = NewCashUpForm(request.POST)
    if not form.is_valid():
        return render(request, "sales/cashup_list.html", {"cus": CashUp.objects.all()[:150], "form": form})
    till = " ".join(form.cleaned_data["till"].split())
    last = CashUp.objects.filter(till__iexact=till, date__lt=form.cleaned_data["date"]).order_by("-date").first()
    cu = CashUp.objects.create(date=form.cleaned_data["date"], till=till, created_by=request.user,
                               cashier=(form.cleaned_data.get("cashier") or "").strip() or request.user.first_name or request.user.username,
                               opening_float=last.float_left if last else Z,
                               float_left=last.float_left if last else Z,
                               zig_rate=CashUp.objects.filter(zig_rate__isnull=False).order_by("-date").values_list("zig_rate", flat=True).first())
    log_change(request.user, "Cash-up", str(cu), "started")
    return redirect("sales:cashup_edit", pk=cu.pk)


def _methods_for(cu):
    used = set(cu.lines.values_list("method_id", flat=True)) if cu.pk else set()
    return [m for m in PaymentMethod.objects.all() if m.active or m.pk in used]


@need("sales", EDIT)
def cashup_edit(request, pk):
    cu = get_object_or_404(CashUp, pk=pk)
    if _locked(request, cu):
        messages.error(request, "This cash-up is signed off. Only the Manager can change it now.")
        return redirect("sales:cashup", pk=pk)
    methods = _methods_for(cu)
    if request.method == "POST":
        hf = CashUpHeaderForm(request.POST, instance=cu)
        tf = TakingsForm(request.POST, methods=methods)
        fs = PayoutFormSet(request.POST, prefix="po")
        if hf.is_valid() and tf.is_valid() and fs.is_valid():
            with transaction.atomic():
                hf.save()
                cu.lines.all().delete()
                for m in methods:
                    till = tf.cleaned_data.get(f"till_{m.pk}")
                    actual = tf.cleaned_data.get(f"actual_{m.pk}")
                    if till is None and actual is None:
                        continue
                    CashUpLine.objects.create(cashup=cu, method=m, till_amount=till or Z, actual_amount=actual)
                cu.expenses.all().delete()
                for f in fs.forms:
                    cd = f.cleaned_data
                    if not cd or cd.get("DELETE") or cd.get("empty"):
                        continue
                    Expense.objects.create(date=cu.date, category=cd["category"], payee=cd.get("payee", ""),
                                           description=cd.get("description", ""), amount=cd["amount"],
                                           receipt_no=cd.get("receipt_no", ""), paid_from=Expense.TILL, cashup=cu,
                                           created_by=request.user)
                res = cu.refresh_totals()
            log_change(request.user, "Cash-up", str(cu), "saved", f"sales {res['total_till']}, over/short {res['variance']}")
            v = res["variance"]
            if v < 0:
                messages.warning(request, f"Cash-up saved. The till is SHORT by ${-v:,.2f}.")
            elif v > 0:
                messages.warning(request, f"Cash-up saved. The till is OVER by ${v:,.2f}.")
            else:
                messages.success(request, "Cash-up saved. It balances.")
            return redirect(reverse("sales:cashup", args=[cu.pk]) + "?saved=1")
    else:
        hf = CashUpHeaderForm(instance=cu)
        init = {}
        for ln in cu.lines.all():
            init[f"till_{ln.method_id}"] = ln.till_amount
            if ln.actual_amount is not None:
                init[f"actual_{ln.method_id}"] = ln.actual_amount
        tf = TakingsForm(initial=init, methods=methods)
        fs = PayoutFormSet(prefix="po", initial=[
            {"category": e.category_id, "payee": e.payee, "description": e.description, "amount": e.amount,
             "receipt_no": e.receipt_no} for e in cu.expenses.all()])
    return render(request, "sales/cashup_form.html", {"cu": cu, "hf": hf, "tf": tf, "fs": fs,
                                                      "cash_ids": [m.pk for m in methods if m.is_cash]})


@need("sales")
def cashup_detail(request, pk):
    from invoices.deliveries import deliveries_on

    cu = get_object_or_404(CashUp.objects.select_related("created_by", "signed_off_by"), pk=pk)
    dels = deliveries_on(cu.date)
    return render(request, "sales/cashup_detail.html", {"cu": cu, "res": cu.result(),
                                                        "payouts": cu.expenses.select_related("category"),
                                                        "dels": dels, "dels_total": sum((d.rung_up or 0 for d in dels), 0),
                                                        "daily_pending": _backup_pending(cu.date)})


def _backup_pending(day):
    """True when this day's cash-ups are not on the flash drive yet (shows the daily-backup pop-up)."""
    try:
        from django.conf import settings as dj
        from core.daily_backup import START, backed_up
        from core.models import CompanySettings
        if getattr(dj, "ONLINE", False):
            return False        # online: the server backs up by itself
        return day >= START and not backed_up(day, CompanySettings.get())
    except Exception:  # noqa: BLE001
        return False


@need("sales")
def cashup_print(request, pk):
    cu = get_object_or_404(CashUp, pk=pk)
    return render(request, "sales/print_cashup.html", {"cu": cu, "res": cu.result(),
                                                       "payouts": cu.expenses.select_related("category")})


@need("sales", EDIT)
@require_POST
def cashup_signoff(request, pk):
    cu = get_object_or_404(CashUp, pk=pk)
    if not _can_manage(request):
        messages.error(request, "Only a manager, supervisor or admin can sign off a cash-up.")
    elif request.POST.get("undo") and rights(request).owner:
        cu.signed_off_by, cu.signed_off_at = None, None
        cu.save()
        log_change(request.user, "Cash-up", str(cu), "sign-off removed")
        messages.success(request, "Sign-off removed – the cash-up can be changed again.")
    elif cu.created_by_id == request.user.pk and not rights(request).owner:
        messages.error(request, "Someone else must sign off a cash-up you did yourself.")
    else:
        cu.signed_off_by, cu.signed_off_at = request.user, timezone.now()
        cu.save()
        log_change(request.user, "Cash-up", str(cu), "signed off")
        messages.success(request, "Cash-up signed off.")
        return redirect(reverse("sales:cashup", args=[pk]) + "?saved=1")
    return redirect("sales:cashup", pk=pk)


@need("sales", EDIT)
@require_POST
def cashup_delete(request, pk):
    cu = get_object_or_404(CashUp, pk=pk)
    if _locked(request, cu):
        messages.error(request, "This cash-up is signed off. Only the Manager can delete it.")
        return redirect("sales:cashup", pk=pk)
    name = str(cu)
    cu.delete()
    log_change(request.user, "Cash-up", name, "deleted")
    messages.success(request, f"{name} deleted.")
    return redirect("sales:cashups")


# ======================================================================= expenses
@need("sales")
def expense_list(request):
    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today)
    start, nxt = month_bounds(month)
    cat = request.GET.get("cat", "")
    qs = Expense.objects.filter(date__gte=start, date__lt=nxt).select_related("category", "cashup", "created_by")
    if cat:
        qs = qs.filter(category_id=cat)
    rows = list(qs)
    by_cat = (Expense.objects.filter(date__gte=start, date__lt=nxt).values("category__name")
              .annotate(t=Sum("amount")).order_by("-t"))
    prev = (start - datetime.timedelta(days=1)).replace(day=1)
    return render(request, "sales/expense_list.html", {
        "rows": rows, "total": sum((e.amount for e in rows), Z), "by_cat": by_cat, "month": start, "prev": prev,
        "next": nxt if nxt <= today.replace(day=1) else None, "cat": cat,
        "cats": ExpenseCategory.objects.all()})


@need("sales", EDIT)
def expense_edit(request, pk=None):
    e = get_object_or_404(Expense, pk=pk) if pk else Expense()
    if e.cashup_id:
        messages.info(request, "This was paid out of the till – change it on the cash-up.")
        return redirect("sales:cashup_edit", pk=e.cashup_id)
    form = ExpenseForm(request.POST or None, instance=e)
    if request.method == "POST" and form.is_valid():
        e = form.save(commit=False)
        if not e.created_by_id:
            e.created_by = request.user
        e.save()
        log_change(request.user, "Expenses", f"{e.category} {e.amount}", "changed" if pk else "added", e.description)
        messages.success(request, "Expense saved.")
        if request.POST.get("another"):
            return redirect("sales:expense_new")
        return redirect(f"/sales/expenses/?month={e.date:%Y-%m}")
    return render(request, "sales/expense_form.html", {"form": form, "e": e})


@need("sales", EDIT)
@require_POST
def expense_delete(request, pk):
    e = get_object_or_404(Expense, pk=pk, cashup__isnull=True)
    month = f"{e.date:%Y-%m}"
    log_change(request.user, "Expenses", f"{e.category} {e.amount}", "deleted", e.description)
    e.delete()
    messages.success(request, "Expense deleted.")
    return redirect(f"/sales/expenses/?month={month}")


# ======================================================================= product sales
@need("sales")
def daysales_list(request):
    days = DaySales.objects.prefetch_related("lines")[:120]
    rows = [(d, d.totals()) for d in days]
    return render(request, "sales/daysales_list.html", {"rows": rows, "form": NewDaySalesForm()})


@need("sales", EDIT)
@require_POST
def daysales_new(request):
    form = NewDaySalesForm(request.POST)
    if not form.is_valid():
        days = DaySales.objects.prefetch_related("lines")[:120]
        return render(request, "sales/daysales_list.html", {"rows": [(d, d.totals()) for d in days], "form": form})
    d = DaySales.objects.create(date=form.cleaned_data["date"], created_by=request.user)
    start = form.cleaned_data["start"]
    log_change(request.user, "Product sales", str(d), "started")
    url = redirect("sales:daysales_edit", pk=d.pk)
    if start == "copy":
        last = DaySales.objects.filter(date__lt=d.date).first()
        if last:
            url["Location"] += f"?from={last.pk}"
    elif start == "all":
        url["Location"] += "?all=1"
    return url


def _product_names():
    return Recipe.objects.filter(active=True, is_subrecipe=False).order_by("name").values_list("name", flat=True)


@need("sales", EDIT)
def daysales_edit(request, pk):
    day = get_object_or_404(DaySales, pk=pk)
    if request.method == "POST":
        fs = SaleLineFormSet(request.POST, prefix="ln")
        if fs.is_valid():
            calc = Calculator().preload()
            old = {ln.recipe_id: ln for ln in day.lines.all()}
            with transaction.atomic():
                day.notes = request.POST.get("notes", "")[:2000]
                day.save()
                day.lines.all().delete()
                pos = 0
                for f in fs.forms:
                    cd = f.cleaned_data
                    if not cd or cd.get("DELETE") or cd.get("empty"):
                        continue
                    r = cd["recipe"]
                    pos += 1
                    o = old.get(r.pk)
                    price = cd.get("price")
                    if price is None:
                        price = o.price if o else (r.sell_price or Z)
                    SaleLine.objects.create(day=day, recipe=r, qty=cd["qty"], price=price, position=pos,
                                            vat_rate=o.vat_rate if o else calc.vat(r),
                                            unit_cost=o.unit_cost if o else (calc.cost_per_unit(r) or Z))
            log_change(request.user, "Product sales", str(day), "saved", f"{pos} products")
            messages.success(request, f"Product sales saved ({pos} products).")
            return redirect("sales:daysales", pk=day.pk)
    else:
        lines = [{"product": ln.recipe.name, "qty": ln.qty.normalize(), "price": ln.price}
                 for ln in day.lines.select_related("recipe")]
        if not lines:
            src = request.GET.get("from")
            if src:
                lines = [{"product": ln.recipe.name} for ln in SaleLine.objects.filter(day_id=src).select_related("recipe")]
            elif request.GET.get("all"):
                lines = [{"product": r.name} for r in Recipe.objects.filter(active=True, is_subrecipe=False,
                                                                            sell_price__isnull=False)
                         .order_by("category__sort_order", "name")]
        fs = SaleLineFormSet(prefix="ln", initial=lines)
    prices = {r.name: float(r.sell_price) for r in Recipe.objects.filter(active=True, sell_price__isnull=False)}
    till = CashUp.objects.filter(date=day.date).aggregate(s=Sum("total_sales"))["s"]
    return render(request, "sales/daysales_form.html", {"day": day, "fs": fs, "names": _product_names(),
                                                        "prices": prices, "till": till})


@need("sales")
def daysales_detail(request, pk):
    day = get_object_or_404(DaySales, pk=pk)
    lines = list(day.lines.select_related("recipe", "recipe__category"))
    till = CashUp.objects.filter(date=day.date).aggregate(s=Sum("total_sales"))["s"]
    t = day.totals()
    return render(request, "sales/daysales_detail.html", {
        "day": day, "lines": lines, "t": t, "till": till,
        "gp": ((t["excl"] - t["cost"]) / t["excl"]) if t["excl"] else None,
        "diff": (t["value"] - till) if till is not None else None})


@need("sales", EDIT)
@require_POST
def daysales_delete(request, pk):
    day = get_object_or_404(DaySales, pk=pk)
    name = str(day)
    day.delete()
    log_change(request.user, "Product sales", name, "deleted")
    messages.success(request, f"{name} deleted.")
    return redirect("sales:daysales_list")


# ======================================================================= report
@need("sales", costs=True)
def report(request):
    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today)
    rep = month_report(month)
    prev = (rep["month"] - datetime.timedelta(days=1)).replace(day=1)
    rep.update({"prev": prev, "next_ok": rep["next"] <= today.replace(day=1)})
    return render(request, "sales/report.html", rep)


# ======================================================================= set-up lists
@need(owner=True)
def setup_lists(request):
    return render(request, "sales/setup.html", {"methods": PaymentMethod.objects.all(),
                                                "cats": ExpenseCategory.objects.all()})


@need(owner=True)
def setup_edit(request, kind, pk=None):
    model, form_cls, label = {"method": (PaymentMethod, PaymentMethodForm, "payment type"),
                              "category": (ExpenseCategory, ExpenseCategoryForm, "expense type")}[kind]
    obj = get_object_or_404(model, pk=pk) if pk else model()
    form = form_cls(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            obj = form.save()
        except IntegrityError:
            form.add_error("name", "That name is already used.")
        else:
            log_change(request.user, "Sales set-up", obj.name, "changed" if pk else "added")
            messages.success(request, f"Saved {obj.name}.")
            return redirect("sales:setup")
    return render(request, "sales/setup_form.html", {"form": form, "obj": obj, "label": label})


# ======================================================================= daily sales (per category)
def _sell_categories(extra_ids=()):
    from costing.models import Category

    used = set(Recipe.objects.filter(active=True, is_subrecipe=False).values_list("category_id", flat=True))
    used |= set(extra_ids)
    return [c for c in Category.objects.all() if c.pk in used]


def _parse_day(s):
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@need("sales")
def daily_list(request):
    from .models import DailySales

    today = timezone.localdate()
    month = parse_month(request.GET.get("month"), today)
    start, nxt = month_bounds(month)
    days = {d.date: d for d in DailySales.objects.filter(date__gte=start, date__lt=nxt)}
    till = {}
    for c in CashUp.objects.filter(date__gte=start, date__lt=nxt):
        till[c.date] = till.get(c.date, Z) + c.total_sales
    rows, wk, mo, gp_mo = [], Z, Z, Z
    d = start
    while d < nxt and d <= max(today, start):
        if d.weekday() == 0:
            wk = Z
        rec = days.get(d)
        if rec:
            wk += rec.total
            mo += rec.total
            gp_mo += rec.gp_amount
        rows.append({"date": d, "rec": rec, "week": wk if rec else None, "month": mo if rec else None,
                     "till": till.get(d), "today": d == today})
        d += datetime.timedelta(days=1)
    rows.reverse()
    prev = (start - datetime.timedelta(days=1)).replace(day=1)
    return render(request, "sales/daily_list.html", {
        "rows": rows, "month": start, "prev": prev, "next": nxt if nxt <= today.replace(day=1) else None,
        "total": mo, "gp": (gp_mo / mo) if mo else None, "n_days": len(days), "today": today,
        "typed_today": today in days})


@need("sales", EDIT)
def daily_edit(request, day):
    from core.targets import product_gps

    from .models import DailySales, DailySalesLine

    d = _parse_day(day)
    if not d:
        return redirect("sales:daily")
    rec = DailySales.objects.filter(date=d).first()
    existing = {ln.category_id: ln.amount for ln in rec.lines.all()} if rec else {}
    cats = _sell_categories(existing.keys())
    errors = []
    if request.method == "POST":
        values = {}
        for c in cats:
            raw = (request.POST.get(f"c{c.pk}") or "").strip().replace(",", "")
            if raw == "":
                continue
            try:
                v = Decimal(raw)
            except Exception:
                errors.append(f"{c.name}: '{raw}' is not an amount.")
                continue
            if v < 0:
                errors.append(f"{c.name}: the amount can't be below 0.")
            elif v:
                values[c] = v.quantize(Decimal("0.01"))
        raw_gp = (request.POST.get("gp") or "").strip().replace("%", "")
        day_gp = None
        if raw_gp:
            try:
                day_gp = Decimal(raw_gp) / 100
                if not (0 <= day_gp < 1):
                    raise ValueError
            except Exception:
                errors.append("GP % must be a number between 0 and 99.")
        if not errors:
            with transaction.atomic():
                if not values:
                    if rec:
                        rec.delete()
                        log_change(request.user, "Daily sales", f"{d:%d %b %Y}", "cleared")
                        messages.success(request, f"Sales for {d:%a %d %b} cleared.")
                    return redirect(f"/sales/daily/?month={d:%Y-%m}")
                cat_gp, avg = product_gps()
                rec = rec or DailySales(date=d, created_by=request.user)
                rec.gp = day_gp
                rec.notes = request.POST.get("notes", "")[:2000]
                rec.save()
                rec.lines.all().delete()
                total = gp_amount = Z
                for c, v in values.items():
                    g = day_gp if day_gp is not None else cat_gp.get(c.pk, avg)
                    DailySalesLine.objects.create(day=rec, category=c, amount=v, gp=g)
                    total += v
                    gp_amount += v * g
                rec.total, rec.gp_amount = total, gp_amount.quantize(Decimal("0.01"))
                rec.save(update_fields=["total", "gp_amount"])
            log_change(request.user, "Daily sales", f"{d:%d %b %Y}", "saved", f"${total}")
            messages.success(request, f"Sales for {d:%a %d %b} saved: ${total:,.2f} excl. VAT.")
            nxt = request.POST.get("go")
            if nxt == "next":
                return redirect("sales:daily_edit", day=(d + datetime.timedelta(days=1)).isoformat())
            if nxt == "dashboard":
                return redirect(f"/?date={d.isoformat()}")
            return redirect(f"/sales/daily/?month={d:%Y-%m}")
        initial = {c.pk: request.POST.get(f"c{c.pk}", "") for c in cats}
        gp_val = request.POST.get("gp", "")
        notes = request.POST.get("notes", "")
    else:
        initial = {c.pk: (existing.get(c.pk) if existing.get(c.pk) is not None else "") for c in cats}
        gp_val = (rec.gp * 100).normalize() if rec and rec.gp is not None else ""
        notes = rec.notes if rec else ""
        if request.GET.get("fill") == "products":
            ps = DaySales.objects.filter(date=d).first()
            if ps:
                sums = {}
                for ln in ps.lines.select_related("recipe"):
                    sums[ln.recipe.category_id] = sums.get(ln.recipe.category_id, Z) + ln.value_excl
                cats = _sell_categories(set(existing.keys()) | set(k for k in sums if k))
                initial = {c.pk: (sums[c.pk].quantize(Decimal("0.01")) if c.pk in sums else "") for c in cats}
                messages.info(request, "Filled in from the product sales of this day – check and save.")
    till = CashUp.objects.filter(date=d).aggregate(s=Sum("total_sales"))["s"]
    from core.models import CompanySettings
    vat = CompanySettings.get().vat_rate
    return render(request, "sales/daily_form.html", {
        "d": d, "rec": rec, "rows": [(c, initial.get(c.pk, "")) for c in cats], "gp_val": gp_val, "notes": notes,
        "errors": errors, "prev": d - datetime.timedelta(days=1), "next": d + datetime.timedelta(days=1),
        "is_future": d > timezone.localdate(), "till": till, "till_excl": (till / (1 + vat)) if till else None,
        "has_products": DaySales.objects.filter(date=d).exists()})


@need("sales")
def daily_today(request):
    return redirect("sales:daily_edit", day=timezone.localdate().isoformat())


# ======================================================================= over & short per cashier
def _period(request):
    """Day, week (Monday–Sunday) or month around the chosen date."""
    kind = request.GET.get("p") if request.GET.get("p") in ("day", "week", "month") else "day"
    try:
        d = datetime.date.fromisoformat(request.GET.get("d", ""))
    except ValueError:
        d = timezone.localdate()
    if kind == "day":
        start = end = d
        prev, nxt = d - datetime.timedelta(days=1), d + datetime.timedelta(days=1)
        label = d.strftime("%A %d %B %Y")
    elif kind == "week":
        start = d - datetime.timedelta(days=d.weekday()); end = start + datetime.timedelta(days=6)
        prev, nxt = start - datetime.timedelta(days=7), start + datetime.timedelta(days=7)
        label = f"Week {start:%d %b} – {end:%d %b %Y}"
    else:
        start = d.replace(day=1)
        end = (start + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)
        prev, nxt = (start - datetime.timedelta(days=1)).replace(day=1), end + datetime.timedelta(days=1)
        label = start.strftime("%B %Y")
    return kind, d, start, end, prev, nxt, label


@need("sales", costs=True)
def cashier_report(request):
    kind, d, start, end, prev, nxt, label = _period(request)
    cus = list(CashUp.objects.filter(date__range=(start, end)).select_related("signed_off_by").order_by("date", "till"))
    people = {}
    for c in cus:
        name = " ".join((c.cashier or "").split()) or "(no cashier named)"
        p = people.setdefault(name, {"name": name, "cus": [], "n": 0, "sales": Z, "over": Z, "short": Z, "net": Z, "waiting": 0})
        v = c.total_variance or Z
        p["cus"].append(c); p["n"] += 1; p["sales"] += c.total_sales or Z; p["net"] += v
        if v > 0: p["over"] += v
        if v < 0: p["short"] += v
        if not c.signed_off_by: p["waiting"] += 1
    rows = sorted(people.values(), key=lambda p: (p["net"], p["name"]))  # biggest short first
    tot = {"n": len(cus), "sales": sum((p["sales"] for p in rows), Z), "over": sum((p["over"] for p in rows), Z),
           "short": sum((p["short"] for p in rows), Z), "net": sum((p["net"] for p in rows), Z),
           "waiting": sum(p["waiting"] for p in rows)}
    tills = {}
    for c in cus:
        t = tills.setdefault(c.till, {"till": c.till, "n": 0, "sales": Z, "net": Z})
        t["n"] += 1; t["sales"] += c.total_sales or Z; t["net"] += c.total_variance or Z
    return render(request, "sales/cashier_report.html", {
        "kind": kind, "d": d, "start": start, "end": end, "prev": prev, "nxt": nxt, "label": label,
        "rows": rows, "tot": tot, "tills": sorted(tills.values(), key=lambda t: t["till"]), "now": timezone.localtime()})
