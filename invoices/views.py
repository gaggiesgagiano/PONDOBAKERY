import datetime

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.access import EDIT, need
from core.models import log_change
from costing.calc import Calculator
from costing.models import Recipe

from .forms import CustomerForm, DocumentForm, LineFormSet, PaidForm
from .models import Customer, DocLine, Document

CUSTOMER_FIELDS = ["name", "company", "address1", "address2", "phone", "email", "vat_no"]


@need("invoices")
def doc_list(request):
    q = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    status = request.GET.get("status", "")
    qs = Document.objects.all()
    if kind:
        qs = qs.filter(kind=kind)
    if status:
        qs = qs.filter(status=status)
    if q:
        num = q.split("-")[-1]
        qs = qs.filter(Q(name__icontains=q) | Q(company__icontains=q) | Q(your_ref__icontains=q)
                       | (Q(seq=int(num)) if num.isdigit() else Q()))
    unpaid = Document.objects.filter(kind=Document.INVOICE, status=Document.OPEN)
    today = timezone.localdate()
    return render(request, "invoices/list.html", {
        "docs": qs[:300], "q": q, "kind": kind, "status": status, "kinds": Document.KINDS, "statuses": Document.STATUS,
        "unpaid_total": unpaid.aggregate(s=Sum("total"))["s"], "unpaid_n": unpaid.count(),
        "overdue_n": unpaid.filter(due__lt=today).count(),
        "open_quotes": Document.objects.filter(kind=Document.QUOTE, status=Document.OPEN).count()})


def _product_names():
    return Recipe.objects.filter(active=True, is_subrecipe=False).order_by("name").values_list("name", flat=True)


@need("invoices", EDIT)
def doc_edit(request, pk=None):
    doc = get_object_or_404(Document, pk=pk) if pk else Document(prepared_by=request.user.first_name or request.user.username)
    if doc.pk and hasattr(doc, "delivery"):
        return redirect("invoices:delivery_edit", pk=doc.delivery.pk)
    if doc.pk and doc.status in (Document.PAID, Document.CANCELLED):
        messages.error(request, "This document is paid or cancelled – re-open it first if it must change.")
        return redirect("invoices:doc", pk=doc.pk)
    if request.method == "POST":
        form = DocumentForm(request.POST, instance=doc)
        fs = LineFormSet(request.POST, prefix="ln")
        if form.is_valid() and fs.is_valid():
            lines = [f.cleaned_data for f in fs.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")
                     and not f.cleaned_data.get("empty")]
            if not lines:
                messages.error(request, "Add at least one product.")
            else:
                calc = Calculator()
                with transaction.atomic():
                    d = form.save(commit=False)
                    if d.customer:  # copy the customer's details unless they were changed on the form
                        for f in CUSTOMER_FIELDS:
                            if not getattr(d, f):
                                setattr(d, f, getattr(d.customer, f))
                    elif form.cleaned_data.get("save_customer") and d.name:
                        d.customer = Customer.objects.create(**{f: getattr(d, f) for f in CUSTOMER_FIELDS})
                    if not d.created_by_id:
                        d.created_by = request.user
                    if not d.due:
                        d.due = d.date + datetime.timedelta(days=14)
                    d.save()
                    d.lines.all().delete()
                    for n, cd in enumerate(lines, 1):
                        r = cd["recipe"]
                        DocLine.objects.create(doc=d, recipe=r, description=cd["description"], qty=cd["qty"],
                                               price=cd["price"], discount=cd["discount"], position=n,
                                               vat_rate=calc.vat(r) if r else calc.settings.vat_rate)
                    d.refresh_totals()
                log_change(request.user, "Invoices", d.number, "changed" if pk else "made", f"{d.name} ${d.total}")
                messages.success(request, f"{d.get_kind_display()} {d.number} saved: ${d.total:,.2f}.")
                return redirect("invoices:doc", pk=d.pk)
    else:
        initial = {}
        if not doc.pk:
            initial["kind"] = request.GET.get("kind") if request.GET.get("kind") in dict(Document.KINDS) else Document.INVOICE
            c = Customer.objects.filter(pk=request.GET.get("customer") or 0).first()
            if c:
                initial.update({"customer": c.pk, **{f: getattr(c, f) for f in CUSTOMER_FIELDS}})
        form = DocumentForm(instance=doc, initial=initial)
        fs = LineFormSet(prefix="ln", initial=[{
            "product": ln.description, "qty": ln.qty.normalize(), "price": ln.price,
            "discount": (ln.discount * 100).normalize() if ln.discount else None} for ln in doc.lines.all()] if doc.pk else [])
    prices = {r.name: float(r.sell_price) for r in Recipe.objects.filter(active=True, sell_price__isnull=False)}
    customers = {c.pk: {f: getattr(c, f) for f in CUSTOMER_FIELDS} for c in Customer.objects.filter(active=True)}
    return render(request, "invoices/form.html", {"doc": doc, "form": form, "fs": fs, "names": _product_names(),
                                                  "prices": prices, "customers": customers})


@need("invoices")
def doc_detail(request, pk):
    doc = get_object_or_404(Document.objects.select_related("customer", "from_doc"), pk=pk)
    return render(request, "invoices/detail.html", {"doc": doc, "lines": doc.lines.all(), "paid_form": PaidForm(),
                                                    "made_from": Document.objects.filter(from_doc=doc)})


@need("invoices")
def doc_print(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    return render(request, "invoices/print.html", {"doc": doc, "lines": doc.lines.all()})


@need("invoices", EDIT)
@require_POST
def doc_status(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    to = request.POST.get("to")
    if to == "paid":
        f = PaidForm(request.POST)
        if f.is_valid():
            doc.status, doc.paid_on, doc.paid_how = Document.PAID, f.cleaned_data["paid_on"], f.cleaned_data["paid_how"]
    elif to in (Document.OPEN, Document.ACCEPTED, Document.CANCELLED):
        doc.status = to
        if to == Document.OPEN:
            doc.paid_on, doc.paid_how = None, ""
    doc.save()
    log_change(request.user, "Invoices", doc.number, f"marked {doc.get_status_display().lower()}")
    messages.success(request, f"{doc.number} is now {doc.get_status_display().lower()}.")
    return redirect("invoices:doc", pk=pk)


@need("invoices", EDIT)
@require_POST
def doc_convert(request, pk):
    src = get_object_or_404(Document, pk=pk)
    kind = request.POST.get("kind")
    if kind not in (Document.PROFORMA, Document.INVOICE):
        return redirect("invoices:doc", pk=pk)
    with transaction.atomic():
        today = timezone.localdate()
        d = Document.objects.create(kind=kind, date=today, due=today + datetime.timedelta(days=14), customer=src.customer,
                                    from_doc=src, your_ref=src.your_ref, notes=src.notes, created_by=request.user,
                                    prepared_by=request.user.first_name or request.user.username,
                                    **{f: getattr(src, f) for f in CUSTOMER_FIELDS})
        for ln in src.lines.all():
            DocLine.objects.create(doc=d, recipe=ln.recipe, description=ln.description, qty=ln.qty, price=ln.price,
                                   discount=ln.discount, vat_rate=ln.vat_rate, position=ln.position)
        d.refresh_totals()
        if src.kind == Document.QUOTE and src.status == Document.OPEN:
            src.status = Document.ACCEPTED
            src.save(update_fields=["status"])
    log_change(request.user, "Invoices", d.number, "made", f"from {src.number}")
    messages.success(request, f"{d.get_kind_display()} {d.number} made from {src.number}.")
    return redirect("invoices:doc", pk=d.pk)


@need("invoices", EDIT)
@require_POST
def doc_delete(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if hasattr(doc, "delivery"):
        messages.error(request, f"This invoice belongs to delivery {doc.delivery.number} – cancel the delivery instead.")
        return redirect("invoices:doc", pk=pk)
    if doc.status == Document.PAID:
        messages.error(request, "A paid document can't be deleted.")
        return redirect("invoices:doc", pk=pk)
    name = doc.number
    doc.delete()
    log_change(request.user, "Invoices", name, "deleted")
    messages.success(request, f"{name} deleted.")
    return redirect("invoices:list")


@need("invoices")
def customer_list(request):
    open_ = {r["customer"]: r["s"] for r in Document.objects.filter(kind=Document.INVOICE, status=Document.OPEN)
             .values("customer").annotate(s=Sum("total"))}
    rows = [(c, open_.get(c.pk)) for c in Customer.objects.all()]
    return render(request, "invoices/customers.html", {"rows": rows})


@need("invoices", EDIT)
def customer_edit(request, pk=None):
    c = get_object_or_404(Customer, pk=pk) if pk else Customer()
    form = CustomerForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        log_change(request.user, "Customers", c.name, "changed" if pk else "added")
        messages.success(request, f"Saved {c.name}.")
        return redirect("invoices:customers")
    docs = c.documents.all()[:30] if c.pk else []
    return render(request, "invoices/customer_form.html", {"form": form, "c": c, "docs": docs})
