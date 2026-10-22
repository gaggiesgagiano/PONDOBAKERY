import os
from decimal import Decimal as D
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from core import mailer
from core.models import Access, EmailLog, EmailSettings


FAKE_PDF = b"%PDF-1.4 fake" + b"x" * 600


class EmailTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("boss", "", "pw")
        self.client.force_login(self.boss)

    def ready(self):
        es = EmailSettings.get()
        es.host, es.username, es.password_enc = "mail.example.test", "jurie@pondobakery.co.zw", mailer.encrypt("s3cret!")
        es.accountant_email = "acc@example.test"
        es.save()
        return es

    def test_password_is_scrambled(self):
        blob = mailer.encrypt("98J+JF(jiQz;")
        self.assertNotIn("98J", blob)
        self.assertEqual(mailer.decrypt(blob), "98J+JF(jiQz;")

    def test_settings_page_keeps_password_and_sends_test(self):
        r = self.client.post("/settings/email/", {"from_name": "Pondo Bakery", "from_email": "jurie@pondobakery.co.zw",
                                                 "host": "mail.example.test", "port": 465, "security": "ssl",
                                                 "username": "jurie@pondobakery.co.zw", "password": "pw1",
                                                 "copy_me": "on", "accountant_email": "", "signature": "Kind regards",
                                                 "test": "1"})
        self.assertEqual(r.status_code, 302)
        es = EmailSettings.get()
        self.assertEqual(mailer.decrypt(es.password_enc), "pw1")
        self.assertTrue(es.last_test_ok)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "Pondo Bakery <jurie@pondobakery.co.zw>")
        # saving again with an empty password keeps the old one
        self.client.post("/settings/email/", {"from_name": "Pondo Bakery", "from_email": "jurie@pondobakery.co.zw",
                                             "host": "mail.example.test", "port": 465, "security": "ssl",
                                             "username": "jurie@pondobakery.co.zw", "password": "",
                                             "accountant_email": "", "signature": "x"})
        self.assertEqual(mailer.decrypt(EmailSettings.get().password_enc), "pw1")
        self.assertNotContains(self.client.get("/settings/email/"), "pw1")

    @mock.patch("core.mailer.html_to_pdf", return_value=FAKE_PDF)
    def test_email_invoice(self, _pdf):
        from invoices.models import Document
        self.ready()
        doc = Document.objects.create(kind="invoice", name="Ann Moyo", email="ann@example.test", seq=1001)
        r = self.client.get(f"/email/doc/{doc.pk}/")
        self.assertContains(r, "ann@example.test")
        r = self.client.post(f"/email/doc/{doc.pk}/", {"to": "ann@example.test", "cc": "", "subject": "Invoice",
                                                      "body": "Hello", "att_pdf": "1"})
        self.assertEqual(r.status_code, 302)
        m = mail.outbox[0]
        self.assertEqual(m.to, ["ann@example.test"])
        self.assertEqual(m.bcc, ["jurie@pondobakery.co.zw"])
        self.assertEqual(m.attachments[0][0], "INV-1001.pdf")
        self.assertIn("Kind regards", m.body)
        self.assertTrue(EmailLog.objects.get().ok)

    @mock.patch("core.mailer.html_to_pdf", return_value=FAKE_PDF)
    def test_email_accountant_report_with_excel(self, _pdf):
        self.ready()
        r = self.client.get("/email/accountant/2026-09/")
        self.assertContains(r, "acc@example.test")
        self.client.post("/email/accountant/2026-09/", {"to": "acc@example.test", "subject": "Report", "body": "Hi",
                                                       "att_pdf": "1", "att_xlsx": "1"})
        names = [a[0] for a in mail.outbox[0].attachments]
        self.assertEqual(names, ["Pondo accountant report 2026-09.pdf", "Pondo accountant report 2026-09.xlsx"])

    def test_bad_address_and_not_set_up(self):
        from invoices.models import Document
        doc = Document.objects.create(kind="quote", name="Ann", seq=1)
        r = self.client.post(f"/email/doc/{doc.pk}/", {"to": "not-an-address", "subject": "x", "body": "y"})
        self.assertContains(r, "not set up yet")
        self.assertEqual(len(mail.outbox), 0)

    def test_cashier_cannot_email_or_open_settings(self):
        from invoices.models import Document
        c = User.objects.create_user("cash", "", "pw")
        Access.from_preset(c, "baker")
        self.client.force_login(c)
        doc = Document.objects.create(kind="invoice", name="Ann", seq=2)
        self.assertEqual(self.client.get(f"/email/doc/{doc.pk}/").status_code, 302)
        self.assertEqual(self.client.get("/settings/email/").status_code, 302)

    def test_real_pdf_when_chrome_is_here(self):
        if not mailer.find_chrome():
            self.skipTest("no Chrome on this machine")
        pdf = mailer.html_to_pdf('<html><head><link rel="stylesheet" href="/static/css/app.css"></head>'
                                 '<body><h1>Pondo</h1><img src="/static/brand/logo/primary_orange.svg"></body></html>')
        self.assertTrue(pdf.startswith(b"%PDF"))
