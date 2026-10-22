from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import CompanySettings
from costing.models import Recipe

from .models import Customer, Document


class InvoiceTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        cs = CompanySettings.get()
        cs.vat_rate = D("0.155")
        cs.save()
        Recipe.objects.create(number=1, name="Birthday Cake", sell_price=D("23.10"))           # normal VAT
        Recipe.objects.create(number=2, name="Bread Loaf", sell_price=D("1.00"), vat_rate=D("0"))  # zero-rated

    def form(self, **extra):
        d = {"kind": "quote", "date": "2026-10-09", "due": "", "customer": "", "name": "Mrs Moyo", "company": "Moyo Events",
             "address1": "", "address2": "", "phone": "0771", "email": "", "vat_no": "", "your_ref": "Wedding",
             "prepared_by": "Jurie", "notes": "", "save_customer": "on",
             "ln-TOTAL_FORMS": "3", "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000",
             "ln-0-product": "birthday cake", "ln-0-qty": "2", "ln-0-price": "", "ln-0-discount": "10",
             "ln-1-product": "Bread Loaf", "ln-1-qty": "50", "ln-1-price": "", "ln-1-discount": "",
             "ln-2-product": "Delivery", "ln-2-qty": "1", "ln-2-price": "11.55", "ln-2-discount": ""}
        d.update(extra)
        return d

    def test_quote_to_invoice_to_paid(self):
        r = self.client.post("/invoices/new/", self.form())
        q = Document.objects.get()
        self.assertRedirects(r, f"/invoices/{q.pk}/", fetch_redirect_response=False)
        self.assertEqual(q.number, "QT-1001")
        # 2 × 23.10 less 10% = 41.58 ; 50 × 1.00 = 50 ; delivery 11.55  -> 103.13
        self.assertEqual(q.total, D("103.13"))
        self.assertEqual(q.subtotal, (D("41.58") / D("1.155") + D("50") + D("11.55") / D("1.155")).quantize(D("0.01")))
        self.assertEqual(q.vat, q.total - q.subtotal)
        self.assertEqual(str(q.due), "2026-10-23")
        self.assertEqual(Customer.objects.get().company, "Moyo Events")
        for url in (f"/invoices/{q.pk}/", f"/invoices/{q.pk}/print/", "/invoices/", "/invoices/customers/",
                    f"/invoices/{q.pk}/edit/", "/invoices/new/?kind=invoice", f"/invoices/customers/{q.customer_id}/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(f"/invoices/{q.pk}/print/"), "QUOTATION")
        self.client.post(f"/invoices/{q.pk}/convert/", {"kind": "invoice"})
        inv = Document.objects.get(kind="invoice")
        q.refresh_from_db()
        self.assertEqual((inv.number, inv.total, inv.from_doc_id, q.status), ("INV-1001", D("103.13"), q.pk, "accepted"))
        self.assertContains(self.client.get(f"/invoices/{inv.pk}/print/"), "TAX INVOICE")
        self.assertContains(self.client.get("/invoices/"), "103.13")
        self.client.post(f"/invoices/{inv.pk}/status/", {"to": "paid", "paid_on": "2026-10-20", "paid_how": "Bank transfer"})
        inv.refresh_from_db()
        self.assertEqual((inv.status, str(inv.paid_on)), ("paid", "2026-10-20"))
        self.assertEqual(self.client.get(f"/invoices/{inv.pk}/edit/").status_code, 302)  # paid = locked
        self.client.post(f"/invoices/{inv.pk}/delete/")
        self.assertTrue(Document.objects.filter(pk=inv.pk).exists())  # paid can't be deleted

    def test_errors_and_second_number(self):
        r = self.client.post("/invoices/new/", self.form(**{"ln-2-price": ""}))
        self.assertContains(r, "Type the price of")
        self.client.post("/invoices/new/", self.form(kind="invoice"))
        self.client.post("/invoices/new/", self.form(kind="invoice", save_customer=""))
        self.assertEqual(sorted(d.number for d in Document.objects.all()), ["INV-1001", "INV-1002"])
        self.assertEqual(Customer.objects.count(), 1)
