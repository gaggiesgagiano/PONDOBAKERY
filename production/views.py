import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need, rights
from core.models import log_change
from costing.calc import Calculator
from costing.models import Recipe
from costing.views import _lines_by_section, method_lines

from .forms import (NewPlanForm, NewWasteForm, PlanHeaderForm, PlanLineFormSet, WasteHeaderForm,
                    WasteLineFormSet)
from .models import WASTE_REASONS, PlanLine, PlanUsage, ProductionPlan, WasteLine, WasteLog
from .plan_calc import PlanResult


def sync_usage(plan):
    """A plan marked Done takes its ingredients out of the store (for stock levels)."""
    plan.refresh_from_db()
    PlanUsage.objects.filter(plan=plan).delete()
    if plan.status != ProductionPlan.DONE:
        if plan.done_at:
            plan.done_at = None
            plan.save(update_fields=["done_at"])
        return
    if not plan.done_at:
        plan.done_at = timezone.now()
        plan.save(update_fields=["done_at"])
    res = PlanResult(plan)
    PlanUsage.objects.bulk_create([PlanUsage(plan=plan, ingredient=d["ingredient"], qty=d["qty"])
                                   for d in res.ingredients.values()])


def _product_names():
    return Recipe.objects.filter(active=True).order_by("name").values_list("name", flat=True)


# ======================================================================= plans
@need("production")
def plan_list(request):
    plans = ProductionPlan.objects.annotate(n=Count("lines")).select_related("planned_by")[:120]
    rows = [(p, sum(ln.units for ln in p.lines.all())) for p in plans]
    return render(request, "production/plan_list.html", {"rows": rows, "form": NewPlanForm(),
                                                         "today": timezone.localdate()})


@need("production", EDIT)
@require_POST
def plan_new(request):
    form = NewPlanForm(request.POST)
    if not form.is_valid():
        plans = ProductionPlan.objects.annotate(n=Count("lines"))[:120]
        rows = [(p, sum(ln.units for ln in p.lines.all())) for p in plans]
        return render(request, "production/plan_list.html", {"rows": rows, "form": form, "today": timezone.localdate()})
    cd = form.cleaned_data
    with transaction.atomic():
        plan = ProductionPlan.objects.create(date=cd["date"], shift=cd["shift"], planned_by=request.user)
        pos = 0
        if cd["start"] == "model":
            field = "par_day" if cd["shift"] == "day" else "par_night"
            for r in Recipe.objects.filter(active=True, is_subrecipe=False, **{f"{field}__gt": 0}).order_by("category__sort_order", "name"):
                pos += 1
                PlanLine.objects.create(plan=plan, recipe=r, model_stock=getattr(r, field), position=pos)
        elif cd["start"] == "copy":
            last = ProductionPlan.objects.filter(shift=cd["shift"], date__lt=cd["date"]).exclude(pk=plan.pk).first()
            if last:
                for ln in last.lines.all():
                    pos += 1
                    PlanLine.objects.create(plan=plan, recipe=ln.recipe, model_stock=ln.model_stock, position=pos,
                                            actual=ln.actual if ln.model_stock == 0 else None)
    log_change(request.user, "Production", str(plan), "plan created")
    if pos == 0 and cd["start"] != "empty":
        messages.info(request, "Nothing to start from yet – add the products below. Tip: set a model stock on each recipe "
                               "and new plans fill themselves.")
    return redirect("production:plan_edit", pk=plan.pk)


@need("production")
def plan_detail(request, pk):
    plan = get_object_or_404(ProductionPlan.objects.select_related("planned_by"), pk=pk)
    res = PlanResult(plan)
    return render(request, "production/plan_detail.html", {"plan": plan, "res": res})


@need("production", EDIT)
def plan_edit(request, pk):
    plan = get_object_or_404(ProductionPlan, pk=pk)
    if request.method == "POST":
        hf = PlanHeaderForm(request.POST, instance=plan)
        fs = PlanLineFormSet(request.POST, prefix="ln")
        if hf.is_valid() and fs.is_valid():
            with transaction.atomic():
                hf.save()
                plan.lines.all().delete()
                pos = 0
                for f in fs.forms:
                    cd = f.cleaned_data
                    if not cd or cd.get("DELETE") or cd.get("empty"):
                        continue
                    pos += 1
                    PlanLine.objects.create(plan=plan, recipe=cd["recipe"], model_stock=cd.get("model_stock") or 0,
                                            on_hand=cd.get("on_hand") or 0, expired=cd.get("expired") or 0,
                                            actual=cd.get("actual"), position=pos)
            sync_usage(plan)
            log_change(request.user, "Production", str(plan), "plan saved")
            messages.success(request, "Plan saved." + (" Ingredients used are taken off the stock." if plan.status == "done" else ""))
            return redirect("production:plan", pk=plan.pk)
    else:
        hf = PlanHeaderForm(instance=plan)
        fs = PlanLineFormSet(prefix="ln", initial=[
            {"product": ln.recipe.name, "model_stock": ln.model_stock, "on_hand": ln.on_hand, "expired": ln.expired,
             "actual": ln.actual} for ln in plan.lines.select_related("recipe")])
    calc = Calculator().preload()
    yields = {r.name: (float(calc.batch_yield(r)) if calc.batch_yield(r) else None)
              for r in Recipe.objects.filter(active=True)}
    return render(request, "production/plan_form.html", {"plan": plan, "hf": hf, "fs": fs, "names": _product_names(),
                                                         "yields": yields})


@need("production", EDIT)
@require_POST
def plan_status(request, pk):
    plan = get_object_or_404(ProductionPlan, pk=pk)
    st = request.POST.get("status")
    if st in dict(ProductionPlan.STATUS):
        plan.status = st
        plan.save(update_fields=["status", "updated_at"])
        sync_usage(plan)
        log_change(request.user, "Production", str(plan), f"marked {plan.get_status_display()}")
        if st == ProductionPlan.DONE:
            messages.success(request, "Plan done – the ingredients it used are taken off the stock.")
    return redirect("production:plan", pk=pk)


@need("production", EDIT)
@require_POST
def plan_delete(request, pk):
    plan = get_object_or_404(ProductionPlan, pk=pk)
    name = str(plan)
    plan.delete()
    log_change(request.user, "Production", name, "plan deleted")
    messages.success(request, f"Plan {name} deleted.")
    return redirect("production:plans")


@need("production")
def plan_print(request, pk, kind):
    plan = get_object_or_404(ProductionPlan, pk=pk)
    res = PlanResult(plan)
    ctx = {"plan": plan, "res": res}
    if kind == "cards":
        cards = []
        for p in res.products:
            r, factor = p["line"].recipe, p["batches"]
            if not factor:
                continue
            secs = _lines_by_section(res.calc, r)
            for sec in secs:
                for it in sec["items"]:
                    it["qty"] = it["qty"] * factor
            cards.append({"r": r, "make": p["units"], "batches": factor, "sections": secs, "method_lines": method_lines(r)})
        for d in res.prepare_rows:
            if not d["batches"]:
                continue
            secs = _lines_by_section(res.calc, d["recipe"])
            for sec in secs:
                for it in sec["items"]:
                    it["qty"] = it["qty"] * d["batches"]
            cards.append({"r": d["recipe"], "make_qty": d["qty"], "unit": d["ingredient"].unit, "batches": d["batches"],
                          "sections": secs, "method_lines": method_lines(d["recipe"]), "mother": True})
        ctx["cards"] = cards
    elif kind not in ("sheet", "pull"):
        return redirect("production:plan", pk=pk)
    return render(request, f"production/print_{kind}.html", ctx)


# ======================================================================= waste
def _waste_rows(logs):
    return [(w, w.lines.count(), w.total_cost) for w in logs]


@need("waste")
def waste_list(request):
    logs = WasteLog.objects.select_related("recorded_by", "signed_off_by").prefetch_related("lines")[:120]
    return render(request, "production/waste_list.html", {"rows": _waste_rows(logs), "form": NewWasteForm()})


@need("waste", EDIT)
@require_POST
def waste_new(request):
    form = NewWasteForm(request.POST)
    if not form.is_valid():
        logs = WasteLog.objects.prefetch_related("lines")[:120]
        return render(request, "production/waste_list.html", {"rows": _waste_rows(logs), "form": form})
    w = WasteLog.objects.create(date=form.cleaned_data["date"], shift=form.cleaned_data["shift"], recorded_by=request.user)
    log_change(request.user, "Waste", str(w), "waste log created")
    return redirect("production:waste_edit", pk=w.pk)


@need("waste", EDIT)
def waste_edit(request, pk):
    w = get_object_or_404(WasteLog, pk=pk)
    if w.signed_off_by and not rights(request).owner:
        messages.error(request, "This waste log is signed off. Only the Operations Manager can change it now.")
        return redirect("production:waste", pk=pk)
    if request.method == "POST":
        hf = WasteHeaderForm(request.POST, instance=w)
        fs = WasteLineFormSet(request.POST, prefix="ln")
        if hf.is_valid() and fs.is_valid():
            calc = Calculator().preload()
            old = {(ln.recipe_id): ln.unit_cost for ln in w.lines.all()}
            with transaction.atomic():
                hf.save()
                w.lines.all().delete()
                for f in fs.forms:
                    cd = f.cleaned_data
                    if not cd or cd.get("DELETE") or cd.get("empty"):
                        continue
                    r = cd["recipe"]
                    uc = old.get(r.pk)
                    if uc is None:
                        uc = calc.cost_per_unit(r) or Decimal("0")
                    WasteLine.objects.create(log=w, recipe=r, qty=cd["qty"], reason=cd["reason"], notes=cd.get("notes", ""),
                                             unit_cost=uc)
            log_change(request.user, "Waste", str(w), "waste log saved")
            messages.success(request, "Waste log saved.")
            return redirect("production:waste", pk=w.pk)
    else:
        hf = WasteHeaderForm(instance=w)
        fs = WasteLineFormSet(prefix="ln", initial=[
            {"product": ln.recipe.name, "qty": ln.qty.normalize(), "reason": ln.reason, "notes": ln.notes}
            for ln in w.lines.select_related("recipe")])
    return render(request, "production/waste_form.html", {"w": w, "hf": hf, "fs": fs, "names": _product_names()})


@need("waste")
def waste_detail(request, pk):
    w = get_object_or_404(WasteLog.objects.select_related("recorded_by", "signed_off_by"), pk=pk)
    lines = list(w.lines.select_related("recipe", "recipe__category"))
    return render(request, "production/waste_detail.html", {"w": w, "lines": lines,
                                                            "total": sum((ln.line_cost for ln in lines), Decimal("0"))})


@need("waste", EDIT)
@require_POST
def waste_signoff(request, pk):
    w = get_object_or_404(WasteLog, pk=pk)
    if not (rights(request).owner or rights(request).costs):
        messages.error(request, "Only a manager, supervisor or admin can sign off waste.")
    else:
        w.signed_off_by, w.signed_off_at = request.user, timezone.now()
        w.save()
        log_change(request.user, "Waste", str(w), "signed off")
        messages.success(request, "Waste log signed off.")
    return redirect("production:waste", pk=pk)


@need("waste", costs=True)
def waste_summary(request):
    today = timezone.localdate()
    try:
        month = datetime.date.fromisoformat(request.GET.get("month", "") + "-01")
    except ValueError:
        month = today.replace(day=1)
    nxt = (month.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    prev = (month - datetime.timedelta(days=1)).replace(day=1)
    lines = WasteLine.objects.filter(log__date__gte=month, log__date__lt=nxt).select_related("recipe", "recipe__category", "log")
    by_day, by_reason, by_product = defaultdict(Decimal), defaultdict(Decimal), defaultdict(lambda: [Decimal(0), Decimal(0)])
    total = Decimal("0")
    for ln in lines:
        c = ln.line_cost
        total += c
        by_day[ln.log.date] += c
        by_reason[ln.reason] += c
        by_product[ln.recipe][0] += ln.qty
        by_product[ln.recipe][1] += c
    days = []
    d = month
    while d < nxt:
        days.append((d, by_day.get(d, Decimal("0"))))
        d += datetime.timedelta(days=1)
    top = sorted(by_product.items(), key=lambda x: -x[1][1])[:15]
    reasons = sorted(by_reason.items(), key=lambda x: -x[1])
    biggest = max([v for _, v in days] + [Decimal("1")])
    from sales.report import sales_total
    sales_excl = sales_total(month, nxt)
    return render(request, "production/waste_summary.html", {
        "sales_excl": sales_excl, "waste_pct": (total / sales_excl) if sales_excl else None,
        "month": month, "prev": prev, "next": nxt if nxt <= today.replace(day=1) else None, "days": days, "total": total,
        "reasons": reasons, "top": top, "biggest": biggest, "logged_days": len(by_day)})
