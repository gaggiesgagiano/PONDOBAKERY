"""E-mail from Pondo: settings (Manager) and the 'E-mail it' page for invoices, quotations, orders and reports.

To add another thing that can be e-mailed later: add one entry to KINDS below.
"""
import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.test import RequestFactory
from django.utils import timezone

from . import mailer
from .access import need, rights
from .models import EmailLog, EmailSettings, Shop, log_change


# ------------------------------------------------------------------ settings
class EmailSettingsForm(forms.ModelForm):
    password = forms.CharField(label="Password", required=False, strip=False,
                               widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
                               help_text="The password of the e-mail box. Leave empty to keep the saved one.")

    class Meta:
        model = EmailSettings
        fields = ["from_name", "from_email", "host", "port", "security", "username", "copy_me", "accountant_email",
                  "signature"]
        widgets = {"signature": forms.Textarea(attrs={"rows": 5})}


@need(owner=True)
def email_settings(request):
    es = EmailSettings.get()
    if request.method == "POST":
        form = EmailSettingsForm(request.POST, instance=es)
        if form.is_valid():
            es = form.save(commit=False)
            if form.cleaned_data["password"]:
                es.password_enc = mailer.encrypt(form.cleaned_data["password"])
            es.save()
            log_change(request.user, "Settings", "E-mail settings", "changed")
            if "test" in request.POST:
                return _send_test(request, es)
            messages.success(request, "E-mail settings saved.")
            return redirect("core:email_settings")
    else:
        form = EmailSettingsForm(instance=es)
    return render(request, "core/email_settings.html", {"form": form, "es": es,
                                                        "log": EmailLog.objects.select_related("user")[:40]})


def _send_test(request, es):
    if not es.ready:
        messages.error(request, "Fill in the server, username and password first.")
        return redirect("core:email_settings")
    ok, err = mailer.send(es, [es.from_email], "Pondo test e-mail",
                          "This is a test from the Pondo Bakery program. E-mail is working.",
                          user=request.user, what="Test e-mail")
    es.last_test, es.last_test_ok = timezone.now(), ok
    es.save(update_fields=["last_test", "last_test_ok"])
    if ok:
        messages.success(request, f"Test e-mail sent to {es.from_email} – check the inbox.")
    else:
        messages.error(request, err)
    return redirect("core:email_settings")


# ------------------------------------------------------------------ what can be e-mailed
def _render(request, view, path, data=None, **kw):
    """Run a print page for the same person and return its HTML."""
    r = RequestFactory().get(path, data or {})
    r.user, r.session = request.user, request.session
    r._messages = getattr(request, "_messages", None)
    resp = view(r, **kw)
    if resp.status_code != 200:
        raise PermissionError("You don't have rights for that page.")
    return resp.content.decode("utf-8")


def _shop():
    s = Shop.objects.filter(active=True).first()
    return s.name if s else "Pondo Bakery"


def k_doc(request, key):
    from invoices.models import Document
    from invoices.views import doc_print

    doc = Document.objects.filter(pk=key).select_related("customer").first()
    if doc is None:
        raise Http404
    to = doc.email or (doc.customer.email if doc.customer else "")
    kind = {"quote": "quotation", "proforma": "pro-forma invoice", "invoice": "tax invoice"}[doc.kind]
    body = (f"Dear {doc.name.split()[0] if doc.name else 'customer'}\n\n"
            f"Please find attached our {kind} {doc.number} for ${doc.total:,.2f}.")
    if doc.kind == Document.QUOTE and doc.due:
        body += f" The quotation is valid until {doc.due:%d %B %Y}."
    elif doc.kind != Document.QUOTE and doc.due and doc.status == Document.OPEN:
        body += f" Payment is due by {doc.due:%d %B %Y}."
    body += "\n\nThank you for choosing Pondo – easy to enjoy!"
    return {"what": f"{doc.title.title()} {doc.number}", "to": to, "subject": f"{doc.title.title()} {doc.number} – {_shop()}",
            "body": body, "back": ("invoices:doc", [doc.pk]), "right": "invoices_edit",
            "files": [("pdf", f"{doc.number}.pdf", lambda: _render(request, doc_print, f"/invoices/{doc.pk}/print/", pk=doc.pk))]}


def k_po(request, key):
    from stock.models import PurchaseOrder
    from stock.views import order_print

    o = PurchaseOrder.objects.filter(pk=key).select_related("supplier").first()
    if o is None:
        raise Http404
    body = (f"Good day {o.supplier.contact or o.supplier.name}\n\nPlease find attached our order {o.number}"
            + (f" for delivery on {o.delivery_date:%A %d %B %Y}" if o.delivery_date else "") +
            ".\nPlease confirm the order and let us know if anything is out of stock.\n\nThank you.")
    return {"what": f"Order {o.number}", "to": o.supplier.email, "subject": f"Order {o.number} – {_shop()}", "body": body,
            "back": ("stock:order", [o.pk]), "right": "stock_edit", "mark_sent": o.status == PurchaseOrder.DRAFT, "obj": o,
            "on_send": lambda user, to, subject, ok, err: o.sends.create(
                how="email", to=", ".join(to)[:300], by=user, ok=ok,
                details=(f"Subject: {subject}" if ok else f"Failed: {err}")[:300]),
            "files": [("pdf", f"Order {o.number}.pdf", lambda: _render(request, order_print, f"/stock/orders/{o.pk}/print/", pk=o.pk))]}


def _month(key):
    try:
        return datetime.date.fromisoformat(key + "-01")
    except ValueError:
        raise Http404


def k_accountant(request, key):
    from reports.accountant_views import accountant_excel, accountant_print

    m = _month(key)
    es = EmailSettings.get()
    return {"what": f"Accountant report {m:%B %Y}", "to": es.accountant_email,
            "subject": f"{_shop()} – month report {m:%B %Y}",
            "body": (f"Good day\n\nPlease find attached the month report of {_shop()} for {m:%B %Y} "
                     f"(1 to {(m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1):%d %B %Y}): "
                     "income statement, VAT, daily sales and takings, expenses, supplier invoices, payroll, invoices, "
                     "stock and equipment. The Excel file has the same figures in one sheet per section.\n\n"
                     "Please let me know if you need anything else."),
            "back": ("reports:month_end", []), "back_q": f"?month={key}", "right": "costs", "month": key,
            "files": [("pdf", f"Pondo accountant report {key}.pdf",
                       lambda: _render(request, accountant_print, "/reports/accountant/", {"month": key})),
                      ("xlsx", f"Pondo accountant report {key}.xlsx",
                       lambda: _render_bytes(request, accountant_excel, "/reports/accountant/excel/", {"month": key}))]}


def k_month_end(request, key):
    from reports.views import month_end_print

    m = _month(key)
    es = EmailSettings.get()
    return {"what": f"Month-end report {m:%B %Y}", "to": es.accountant_email, "subject": f"{_shop()} – month-end {m:%B %Y}",
            "body": f"Good day\n\nPlease find attached the one-page month-end report of {_shop()} for {m:%B %Y}.",
            "back": ("reports:month_end", []), "back_q": f"?month={key}", "right": "costs",
            "files": [("pdf", f"Pondo month-end {key}.pdf",
                       lambda: _render(request, month_end_print, "/reports/print/", {"month": key}))]}


def _render_bytes(request, view, path, data=None):
    r = RequestFactory().get(path, data or {})
    r.user, r.session = request.user, request.session
    r._messages = getattr(request, "_messages", None)
    resp = view(r)
    if resp.status_code != 200:
        raise PermissionError("You don't have rights for that page.")
    return resp.content


KINDS = {"doc": k_doc, "po": k_po, "accountant": k_accountant, "month_end": k_month_end}
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class ComposeForm(forms.Form):
    to = forms.CharField(label="To", help_text="Several addresses: separate with commas")
    cc = forms.CharField(label="CC", required=False)
    subject = forms.CharField(max_length=200)
    body = forms.CharField(label="Message", widget=forms.Textarea(attrs={"rows": 9}))

    def _addresses(self, field, required):
        out = mailer.split_addresses(self.cleaned_data.get(field, ""))
        if required and not out:
            raise forms.ValidationError("Type at least one e-mail address.")
        bad = [a for a in out if not mailer.valid_address(a)]
        if bad:
            raise forms.ValidationError("Not an e-mail address: " + ", ".join(bad))
        return out

    def clean_to(self):
        return self._addresses("to", True)

    def clean_cc(self):
        return self._addresses("cc", False)


@login_required
def email_compose(request, kind, key):
    fn = KINDS.get(kind)
    if fn is None:
        raise Http404
    can = rights(request)
    k = fn(request, key)
    if not getattr(can, k["right"], False):
        messages.error(request, "You don't have rights to e-mail this. Ask the Manager.")
        return redirect("core:dashboard")
    es = EmailSettings.get()
    back = k["back"]
    from django.urls import reverse
    back_url = reverse(back[0], args=back[1]) + k.get("back_q", "")
    if request.method == "POST":
        form = ComposeForm(request.POST)
        chosen = [f for f in k["files"] if request.POST.get("att_" + f[0])]
        if not es.ready:
            messages.error(request, "E-mail is not set up yet – the Manager fills it in under Settings › E-mail.")
        elif form.is_valid():
            try:
                atts = []
                for ext, name, make in chosen:
                    data = make()
                    atts.append((name, mailer.html_to_pdf(data) if ext == "pdf" else data, MIME[ext]))
            except Exception as e:  # noqa: BLE001
                messages.error(request, f"The attachment could not be made: {e}")
                return render(request, "core/email_compose.html", {"form": form, "k": k, "es": es, "back_url": back_url})
            ok, err = mailer.send(es, form.cleaned_data["to"], form.cleaned_data["subject"], form.cleaned_data["body"],
                                  atts, cc=form.cleaned_data["cc"], user=request.user, what=k["what"])
            if k.get("on_send"):
                k["on_send"](request.user, form.cleaned_data["to"] + form.cleaned_data["cc"],
                             form.cleaned_data["subject"], ok, err)
            if ok:
                if k.get("mark_sent") and request.POST.get("mark_sent"):
                    o = k["obj"]
                    o.status = o.SENT
                    o.save(update_fields=["status"])
                log_change(request.user, "E-mail", k["what"], "e-mailed", ", ".join(form.cleaned_data["to"]))
                messages.success(request, f"{k['what']} e-mailed to {', '.join(form.cleaned_data['to'])}.")
                return redirect(back_url)
            messages.error(request, err)
    else:
        form = ComposeForm(initial={"to": k["to"], "subject": k["subject"], "body": k["body"]})
    return render(request, "core/email_compose.html", {"form": form, "k": k, "es": es, "back_url": back_url})
