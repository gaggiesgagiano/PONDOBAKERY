import json
import shutil
import tempfile
from decimal import Decimal as D
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.models import Access
from costing.models import Category, Ingredient, Recipe, RecipeLine
from sales.models import PaymentMethod
from till.models import Sale, Shift, Till

from . import engine as eng
from . import service
from .models import FiscalCall, FiscalSetup


def env(code, message="", data=""):
    return {"Code": str(code), "Message": message, "Data": data if isinstance(data, str) else json.dumps(data)}


def receipt_xml(inv, gno, sync="submitted", day="12"):
    return (f"<ReceiptData><DeviceID>18084</DeviceID><InvoiceNumber>{inv}</InvoiceNumber><FDMSData><DeviceID>18084</DeviceID>"
            f"<FiscalDayNo>{day}</FiscalDayNo><ReceiptGlobalNo>{gno}</ReceiptGlobalNo>"
            f"<QRCode>https://fdmstest.zimra.co.zw/000001808422102026{gno:010d}ABCDEF0123456789</QRCode>"
            f"<SyncState>{sync}</SyncState></FDMSData></ReceiptData>")


class FakeEngine:
    """Answers like FiscalStackZW.dll, and remembers every call."""

    def __init__(self):
        self.calls = []
        self.day = "FiscalDayOpened"
        self.sync = "submitted"
        self.refuse = None
        self.gno = 100
        self.seen = set()

    def installed(self):
        return True

    def restart(self):
        self.calls.append(("restart",))

    def stop(self):
        pass

    def call(self, method, *args, timeout=None):
        self.calls.append((method, *args))
        if method == "GetStatus":
            return env(1, "ok", {"FiscalDayStatus": self.day, "LastFiscalDayNo": 12, "zimraReachable": True})
        if method == "OpenDay":
            self.day = "FiscalDayOpened"
            return env(1, "Success", {"fiscalDayNo": 13})
        if method == "CheckLicense":
            return env(1, "Success", {"allowed": True, "inGrace": False})
        if method == "GetDeviceStatus":
            return env(1, "ok", "<DeviceStatus><Status>Online</Status><DeviceID>18084</DeviceID></DeviceStatus>")
        if method == "TransactM":
            inv = args[2]
            if self.day != "FiscalDayOpened":
                return env(0, "Transaction error: fiscal day is closed")
            if self.refuse:
                return env(0, self.refuse)
            if inv in self.seen:
                return env(0, f"Transaction error: Internal validation - invoice number '{inv}' was already used on this device.")
            self.seen.add(inv)
            self.gno += 1
            return env(1, "Success", receipt_xml(inv, self.gno, self.sync))
        if method == "GetTransaction":
            return env(1, "ok", {"InvoiceNumber": args[0], "ReceiptQRCode": "https://fdmstest.zimra.co.zw/RECOVERED",
                                 "GlobalReceiptNumber": 555, "FiscalDayNumber": "12", "FiscalSyncStatus": "synced"})
        if method == "SubmitPendingQueue":
            items = [{"invoiceNumber": s.fiscal_ref, "status": "synced", "globalReceiptNo": 900}
                     for s in Sale.objects.filter(fiscal_status="pending")]
            return env(1, "ok", {"total": len(items), "submitted": len(items), "failed": 0, "stillPending": 0, "items": items})
        if method == "ZReport":
            self.day = "FiscalDayClosed"
            return env(1, "Success", "<FiscalDayReport/>")
        return env(1, "ok", "")

    def methods(self):
        return [c[0] for c in self.calls]


class FiscalTillTests(TestCase):
    def setUp(self):
        self.fake = FakeEngine()
        eng.set_engine(self.fake)
        service._day.update(open=False, checked=0.0)
        self.owner = User.objects.create_superuser("boss", password="Boss-pass-1")
        self.cashier = User.objects.create_user("rudo", password="Rudo-pass-1", first_name="Rudo")
        Access.from_preset(self.cashier, "cashier")
        self.sup = User.objects.create_user("sid", password="Sid-pass-1")
        Access.from_preset(self.sup, "supervisor")
        cat = Category.objects.create(name="Pies")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("1"))
        self.pie = Recipe.objects.create(number=201254, name="Pondo Cheeseburger Pie & Co", scaling_weight=D("0.5"),
                                         sell_price=D("2.50"), vat_rate=D("0.155"), category=cat)
        self.bread = Recipe.objects.create(number=101, name="White bread", sell_price=D("1.20"), vat_rate=D("0"),
                                           category=cat, sold_per="kg")
        RecipeLine.objects.create(recipe=self.pie, ingredient=flour, qty=10)
        self.cash = PaymentMethod.objects.get(name="Cash (US$)")
        self.till = Till.objects.get(name="Till 1")
        FiscalSetup.objects.create(mode=FiscalSetup.TEST, hs_code="19059000")
        from core.models import CompanySettings
        cs = CompanySettings.get()
        cs.zwg_rate = D("26.5")
        cs.save()

    def tearDown(self):
        eng.set_engine(None)

    def open_till(self):
        self.client.login(username="rudo", password="Rudo-pass-1")
        self.client.post("/till/", {"till": self.till.pk, "float": "200", "zig_rate": "26.5"})
        return Shift.objects.get()

    def sell(self, sh, items, payments):
        return self.client.post(f"/till/{sh.pk}/sell/", json.dumps({"items": items, "payments": payments}),
                                content_type="application/json").json()

    def test_sale_becomes_fiscal_receipt(self):
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 3}, {"id": self.bread.pk, "qty": "0.75"}],
                      [{"method": self.cash.pk, "amount": "10"}, {"method": self.cash.pk, "zig": "26.5"}])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fiscal"], "submitted")
        sale = Sale.objects.get(number=r["number"])
        self.assertRegex(sale.fiscal_ref, r"^\d{14}$")                     # YYYYMMDDHHMMSS
        self.assertEqual((sale.fiscal_status, sale.fiscal_global_no, sale.fiscal_day, sale.fiscal_mode),
                         ("submitted", "101", "12", "test"))
        self.assertTrue(sale.fiscal_qr.startswith("https://fdmstest.zimra.co.zw/"))
        call = next(c for c in self.fake.calls if c[0] == "TransactM")
        (_, cur, email, inv, name, vatno, addr, phone, tin, amount, tax, flag, comment, orig, items, currencies) = call
        self.assertEqual((cur, inv, amount, tax, flag, orig), ("USD", sale.fiscal_ref, "8.40", "1.01", "01", ""))
        self.assertIn("<QTY>0.75</QTY><PRICE>1.20</PRICE><AMT>0.90</AMT><TAX>0.00</TAX><TAXR>0</TAXR>", items)
        self.assertIn("<HH>19059000</HH><ITEMCODE>201254</ITEMCODE><ITEMNAME1>Pondo Cheeseburger Pie &amp; Co</ITEMNAME1>", items)
        self.assertIn("<QTY>3</QTY><PRICE>2.50</PRICE><AMT>7.50</AMT><TAX>1.01</TAX><TAXR>0.155</TAXR>", items)
        self.assertIn("<Name>USD</Name><Amount>8.40</Amount>", currencies)   # payments = total, ZiG counted in US$
        page = self.client.get(f"/till/receipt/{sale.pk}/")
        self.assertContains(page, "FISCAL TAX INVOICE")
        self.assertContains(page, "ZIMRA TEST – NOT A TAX INVOICE")
        self.assertContains(page, "<svg")
        self.assertNotContains(page, "PRACTICE – NOT A TAX INVOICE")
        self.assertTrue(FiscalCall.objects.filter(method="TransactM", sale=sale, ok=True).exists())

    def test_refund_is_credit_note_with_positive_lines(self):
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 2}], [{"method": self.cash.pk, "amount": "5"}])
        sale = Sale.objects.get(number=r["number"])
        item = sale.items.get()
        self.client.post(f"/till/{sh.pk}/refund/{sale.pk}/", {f"q{item.pk}": "1", "reason": "wrong pie", "method": self.cash.pk,
                                                              "by": "sid", "pw": "Sid-pass-1"})
        rf = Sale.objects.get(kind="refund")
        self.assertEqual(rf.fiscal_status, "submitted")
        call = [c for c in self.fake.calls if c[0] == "TransactM"][-1]
        self.assertEqual((call[9], call[11], call[13]), ("2.50", "02", sale.fiscal_ref))   # amount, flag, original invoice
        self.assertIn("wrong pie", call[12])                                           # receiptNotes (RCPT034)
        self.assertIn("<QTY>1</QTY><PRICE>2.50</PRICE><AMT>2.50</AMT>", call[14])      # engine makes them negative
        self.assertContains(self.client.get(f"/till/receipt/{rf.pk}/"), "FISCAL CREDIT NOTE")

    def test_customer_details_on_slip_and_to_zimra(self):
        sh = self.open_till()
        body = lambda c: json.dumps({"items": [{"id": self.pie.pk, "qty": 2}],
                                     "payments": [{"method": self.cash.pk, "amount": "5"}], "customer": c})
        post = lambda c: self.client.post(f"/till/{sh.pk}/sell/", body(c), content_type="application/json").json()
        r = post({"name": "Acme Foods (Pvt) Ltd", "tin": "20016883", "vat": "", "save": True})
        self.assertFalse(r["ok"])
        self.assertIn("10 digits", r["error"])
        self.assertTrue(r["customer_error"])
        self.assertEqual(Sale.objects.count(), 0)            # nothing saved while the details are wrong
        self.assertIn("name", post({"tin": "2001688329"})["error"])
        r = post({"name": "Acme Foods (Pvt) Ltd", "tin": "2001688329", "vat": "220413865", "address": "1 Main St, Harare",
                  "email": "accounts@acme.co.zw", "phone": "+263 77 123 4567", "save": True})
        self.assertTrue(r["ok"], r)
        sale = Sale.objects.get(number=r["number"])
        self.assertEqual((sale.customer_name, sale.customer_tin, sale.customer_vat), ("Acme Foods (Pvt) Ltd", "2001688329", "220413865"))
        from invoices.models import Customer
        cust = Customer.objects.get(tin="2001688329")              # saved for next time
        self.assertEqual(sale.customer, cust)
        call = [c for c in self.fake.calls if c[0] == "TransactM"][-1]
        # email, invoice, name, VAT, address, phone, TIN – in the engine's order
        self.assertEqual(call[2:9], ("accounts@acme.co.zw", sale.fiscal_ref, "Acme Foods (Pvt) Ltd", "220413865",
                                     "1 Main St, Harare", "+263 77 123 4567", "2001688329"))
        page = self.client.get(f"/till/receipt/{sale.pk}/")
        for text in ('<td class="b">Customer:</td><td>Acme Foods (Pvt) Ltd</td>', '<td class="b">TIN no:</td><td>2001688329</td>', "220413865", "accounts@acme.co.zw", "Verification code", "15.5%"):
            self.assertContains(page, text)
        # the till screen offers the saved customer next time
        self.assertIn("Acme Foods (Pvt) Ltd", [c["name"] for c in json.loads(self.client.get(f"/till/{sh.pk}/").context["customers_json"])])
        # a refund (credit note) goes to the same customer
        item = sale.items.get()
        self.client.post(f"/till/{sh.pk}/refund/{sale.pk}/", {f"q{item.pk}": "1", "reason": "stale", "method": self.cash.pk,
                                                              "by": "sid", "pw": "Sid-pass-1"})
        rf = Sale.objects.get(kind="refund")
        self.assertEqual((rf.customer_name, rf.customer_tin), ("Acme Foods (Pvt) Ltd", "2001688329"))
        self.assertEqual([c for c in self.fake.calls if c[0] == "TransactM"][-1][8], "2001688329")
        # no details asked for: walk-in, nothing extra on the slip
        r = post(None)
        sale = Sale.objects.get(number=r["number"])
        self.assertEqual(sale.customer_name, "")
        self.assertNotContains(self.client.get(f"/till/receipt/{sale.pk}/"), "Customer:")

    def test_paid_all_in_zwg_receipt_and_zimra_in_zwg(self):
        sh = self.open_till()
        post = lambda pays: self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "26.5", "items": [{"id": self.pie.pk, "qty": 3}, {"id": self.bread.pk, "qty": "0.75"}],
            "payments": pays}), content_type="application/json").json()
        # ZWG 2.50 x 26.5 = 66.25 each; bread 1.20 x 26.5 = 31.80/kg x 0.75 = 23.85 → ZWG 222.60
        self.assertIn("ZWG 0.10", post([{"method": self.cash.pk, "zig": "222.50"}])["error"])
        r = post([{"method": self.cash.pk, "zig": "230"}])
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["currency"], r["change_fx"]), ("ZWG", "7.40"))
        sale = Sale.objects.get(number=r["number"])
        self.assertEqual((sale.currency, sale.total_fx, sale.vat_fx, sale.change_fx, sale.fx_rate),
                         ("ZWG", D("222.60"), D("26.67"), D("7.40"), D("26.5")))
        self.assertEqual(sale.total, D("8.40"))                                    # the books stay in US$
        self.assertEqual(sum(p.amount for p in sale.payments.all()), D("8.40"))     # cash-up adds up in US$
        call = [c for c in self.fake.calls if c[0] == "TransactM"][-1]
        self.assertEqual((call[1], call[9], call[10]), ("ZWG", "222.60", "26.67"))
        self.assertIn("<QTY>3</QTY><PRICE>66.25</PRICE><AMT>198.75</AMT>", call[14])
        self.assertIn("<QTY>0.75</QTY><PRICE>31.80</PRICE><AMT>23.85</AMT>", call[14])
        self.assertIn("<Name>ZWG</Name><Amount>222.60</Amount>", call[15])
        page = self.client.get(f"/till/receipt/{sale.pk}/")
        for text in ("TOTAL ZWG", "222.60", "26.67", "CHANGE ZWG", "7.40", "3 x 66.25", "198.75", "ZWG 26.50 = USD 1", "ZWG Cash"):
            self.assertContains(page, text)
        self.assertNotContains(page, "TOTAL US$")
        # refund one pie: a ZWG credit note at the sale's rate, even after the rate changed
        from core.models import CompanySettings
        cs = CompanySettings.get()
        cs.zwg_rate = D("30")
        cs.save()
        pie = sale.items.get(recipe=self.pie)
        self.client.post(f"/till/{sh.pk}/refund/{sale.pk}/", {f"q{pie.pk}": "1", "reason": "squashed", "method": self.cash.pk,
                                                              "by": "sid", "pw": "Sid-pass-1"})
        rf = Sale.objects.get(kind="refund")
        self.assertEqual((rf.currency, rf.total_fx, rf.fx_rate, rf.payments.get().zig_amount), ("ZWG", D("-66.25"), D("26.5"), D("-66.25")))
        call = [c for c in self.fake.calls if c[0] == "TransactM"][-1]
        self.assertEqual((call[1], call[9], call[11]), ("ZWG", "66.25", "02"))
        self.assertContains(self.client.get(f"/till/receipt/{rf.pk}/"), "TOTAL ZWG")
        # part USD, part ZWG: one currency per receipt, so it stays a US$ receipt
        r = self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "30", "items": [{"id": self.pie.pk, "qty": 2}],
            "payments": [{"method": self.cash.pk, "amount": "2.50"}, {"method": self.cash.pk, "zig": "75"}]}),
            content_type="application/json").json()
        self.assertEqual(Sale.objects.get(number=r["number"]).currency, "USD")
        self.assertEqual([c for c in self.fake.calls if c[0] == "TransactM"][-1][1], "USD")

    def test_invoice_number_is_the_moment_of_the_sale(self):
        from unittest import mock
        sh = self.open_till()
        with mock.patch("till.views._invoice_no", return_value="20261022161105"):
            a = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
            b = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])  # same second
        sa, sb = Sale.objects.get(number=a["number"]), Sale.objects.get(number=b["number"])
        self.assertEqual((sa.fiscal_ref, sb.fiscal_ref), ("20261022161105", "20261022161105-2"))
        self.assertContains(self.client.get(f"/till/receipt/{sa.pk}/"), "20261022161105")
        self.assertContains(self.client.get(f"/till/{sh.pk}/sales/?q=20261022161105"), sb.number)
        FiscalSetup.objects.update(mode=FiscalSetup.OFF)            # practice slips get one too
        c = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertTrue(Sale.objects.get(number=c["number"]).fiscal_ref.isdigit())

    def test_red_receipt_is_signed_and_printed_with_qr(self):
        """ZIMRA stores a receipt but flags it red: it is signed and final – the slip prints with its QR code."""
        import hashlib, base64
        sig = "ke+KZATIREQ1w9QUzeZOz8mvz/glDLXbmGUTq1ozrQznMzsngSPhiHcxzCtkxDlJU/M+kUTwwnhI6KvkseiuVxYljoLBMaYXmuBKjY6412aOrbEYXyiEgbhlvwIocQbde+cVTOu7wN6evw+BADWV+iV0IBt32NdEgE83PlvETNyMrP7gCaHMRnwN+YrC+yoeYto5e0aD60DwenbdzzHUEqpj7URobpAT4i13ihbFTNgQgUSd3zS4vtwbHmL32LEeWVF/VXuQUrFlygnwwmaodvjxrDyoPR3giE3R9292OjqheQpTsKXlIrUkLMQYWFcoHKkSYsIVUbP4TEX81u+bgg=="
        fake = self.fake
        red = ("Transaction error: ZIMRA FDMS error - invoice {inv} was stored by ZIMRA but flagged with RED validation "
               "errors; the receipt is INVALID and will not be chained. ZIMRA response: ")
        orig_call = fake.call
        def call(method, *args, timeout=None):
            if method == "TransactM":
                fake.calls.append((method, *args))
                fake.last_inv = args[2]
                return env(0, red.format(inv=args[2]))
            if method == "GetTransaction":
                fake.calls.append((method, *args))
                rec = {"receiptGlobalNo": 51, "receiptDate": "2026-10-22T17:45:34",
                       "receiptDeviceSignature": {"hash": "x", "signature": sig}}
                return env(1, "ok", {"InvoiceNumber": args[0], "ReceiptQRCode": "", "GlobalReceiptNumber": 51,
                                     "FiscalDayNumber": "16", "DeviceID": "38529", "FiscalSyncStatus": "",
                                     "JsonData": json.dumps(rec)})
            return orig_call(method, *args, timeout=timeout)
        fake.call = call
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "flagged")
        self.assertIn("flagged it red", r["fiscal_note"])
        sale = Sale.objects.get()
        md5 = hashlib.md5(base64.b64decode(sig)).hexdigest().upper()[:16]
        self.assertEqual(sale.fiscal_qr, f"https://fdmstest.zimra.co.zw/0000038529221020260000000051{md5}")
        self.assertEqual((sale.fiscal_global_no, sale.fiscal_day, sale.fiscal_ref), ("51", "16", fake.last_inv))
        page = self.client.get(f"/till/receipt/{sale.pk}/")
        self.assertContains(page, "<svg")
        self.assertContains(page, "-".join(md5[i:i + 4] for i in range(0, 16, 4)))     # verification code
        self.assertContains(page, "ZIMRA validation: RED")
        n = sum(1 for c in fake.calls if c[0] == "TransactM")
        self.client.login(username="sid", password="Sid-pass-1")
        self.assertContains(self.client.get("/fiscal/"), "flagged red")
        self.client.post("/fiscal/do/", {"do": "retry"})          # nothing to retry: flagged receipts are final
        self.assertEqual(sum(1 for c in fake.calls if c[0] == "TransactM"), n)
        # a refund of a flagged slip is still a credit note against it
        fake.call = orig_call
        self.client.login(username="rudo", password="Rudo-pass-1")
        self.client.post(f"/till/{sh.pk}/refund/{sale.pk}/", {f"q{sale.items.get().pk}": "1", "reason": "x",
                                                              "method": self.cash.pk, "by": "sid", "pw": "Sid-pass-1"})
        self.assertEqual(Sale.objects.get(kind="refund").fiscal_status, "submitted")

    def test_retry_uses_the_receipt_the_engine_already_signed(self):
        sh = self.open_till()
        self.fake.refuse = "Transaction error: engine busy (counter lock timeout). Try again."
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "failed")
        self.fake.refuse = None
        self.client.login(username="sid", password="Sid-pass-1")
        self.client.post("/fiscal/do/", {"do": "retry"})
        sale = Sale.objects.get()
        self.assertEqual(sale.fiscal_status, "submitted")          # the fake has a stored row → recovered, not resent
        self.assertEqual([c[0] for c in self.fake.calls].count("TransactM"), 1)

    def test_offline_sale_is_pending_then_synced(self):
        self.fake.sync = "pending"
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "pending")
        self.assertIn("Keep selling", r["fiscal_note"])
        self.client.login(username="sid", password="Sid-pass-1")
        self.client.post("/fiscal/do/", {"do": "sync"})
        sale = Sale.objects.get()
        self.assertEqual((sale.fiscal_status, sale.fiscal_global_no, sale.fiscal_qr),
                         ("submitted", "555", "https://fdmstest.zimra.co.zw/RECOVERED"))

    def test_refused_sale_is_kept_and_can_be_retried(self):
        self.fake.refuse = "Transaction error: Internal validation - pre-submission compliance check rejected receipt"
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertTrue(r["ok"])                       # the sale itself is never lost
        self.assertEqual(r["fiscal"], "failed")
        self.assertIn("NOT fiscalised", r["fiscal_note"])
        sale = Sale.objects.get()
        self.assertContains(self.client.get(f"/till/receipt/{sale.pk}/"), "NOT YET FISCALISED")
        self.fake.refuse = None
        self.client.login(username="rudo", password="Rudo-pass-1")
        self.client.post("/fiscal/do/", {"do": "retry"})        # a cashier may not
        self.assertEqual(Sale.objects.get().fiscal_status, "failed")
        self.client.login(username="sid", password="Sid-pass-1")
        self.assertContains(self.client.get("/fiscal/"), sale.number)
        self.client.post("/fiscal/do/", {"do": "retry"})
        self.assertEqual(Sale.objects.get().fiscal_status, "submitted")

    def test_closed_day_is_opened_by_itself(self):
        self.fake.day = "FiscalDayClosed"
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "submitted")
        m = self.fake.methods()
        self.assertLess(m.index("OpenDay"), m.index("TransactM"))

    def test_already_used_invoice_is_recovered(self):
        sh = self.open_till()
        from unittest import mock
        self.fake.seen.add("20261022120000")    # the engine made it, but Pondo stopped before saving the answer
        with mock.patch("till.views._invoice_no", return_value="20261022120000"):
            r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "submitted")
        self.assertEqual(Sale.objects.get().fiscal_qr, "https://fdmstest.zimra.co.zw/RECOVERED")

    def test_off_and_demo_never_fiscalise(self):
        FiscalSetup.objects.update(mode=FiscalSetup.OFF)
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
        self.assertEqual(r["fiscal"], "practice")
        FiscalSetup.objects.update(mode=FiscalSetup.LIVE)
        with self.settings():
            import os
            os.environ["PONDO_DEMO"] = "1"
            try:
                r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}])
            finally:
                del os.environ["PONDO_DEMO"]
        self.assertEqual(r["fiscal"], "practice")
        self.assertNotIn("TransactM", self.fake.methods())

    def test_close_day_sends_waiting_then_z_report(self):
        self.client.login(username="sid", password="Sid-pass-1")
        self.client.post("/fiscal/do/", {"do": "close"})
        m = self.fake.methods()
        self.assertLess(m.index("SubmitPendingQueue"), m.index("ZReport"))
        self.assertNotIn("CloseDay", m)             # ZReport closes the day on ZIMRA itself

    def test_pages(self):
        self.client.login(username="sid", password="Sid-pass-1")
        self.assertContains(self.client.get("/fiscal/"), "Close fiscal day")
        self.assertEqual(self.client.get("/fiscal/setup/").status_code, 302)      # Manager only
        self.client.login(username="boss", password="Boss-pass-1")
        self.assertEqual(self.client.get("/fiscal/journal/").status_code, 200)
        self.assertContains(self.client.get("/"), "Fiscal (ZIMRA)")


class FiscalSetupTests(TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "FiscalStackZW.dll").write_bytes(b"")
        (self.dir / "config.ini").write_text("[FISCALSTACKZW]\nDEVICEID=18084\nZIMRASERVER=https://fdmsapi.zimra.co.zw\n"
                                             "TAXIDSTANDARDRATED=515\nLICENSEGRACE=7\n", encoding="utf-8")
        self.fake = FakeEngine()
        eng.set_engine(self.fake)
        User.objects.create_superuser("boss", password="Boss-pass-1")
        self.client.login(username="boss", password="Boss-pass-1")

    def tearDown(self):
        eng.set_engine(None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_test_mode_writes_config_and_live_needs_confirmation(self):
        with override_settings(FISCAL_ENGINE_DIR=self.dir), self.settings():
            import os
            pd = os.environ.pop("PROGRAMDATA", None)
            try:
                form = {"do": "save", "mode": "test", "hs_code": "1905 9000", "auto_open_day": "on",
                        "DEVICEBRANCHNAME": "Pondo Bakery", "DEVICESTREET": "Chinhoyi Street", "DEVICEHOUSENO": "74",
                        "DEVICECITY": "Harare", "DEVICEPROVINCE": "Harare"}
                self.client.post("/fiscal/setup/", form)
                cfg = eng.read_config()
                self.assertEqual((cfg["ZIMRASERVER"], cfg["POSENVIRONMENT"], cfg["TAXIDSTANDARDRATED"], cfg["TAXIDEXEMPTED"]),
                                 ("https://fdmsapitest.zimra.co.zw", "TEST", "517", "3"))
                self.assertEqual((cfg["DEVICEID"], cfg["LICENSEGRACE"], cfg["DEVICEHOUSENO"], cfg["VATFLAG"]),
                                 ("18084", "7", "74", "1"))     # other keys kept
                self.assertEqual(FiscalSetup.get().hs_code, "19059000")
                self.assertIn(("restart",), self.fake.calls)
                self.client.post("/fiscal/setup/", {**form, "mode": "live"})
                self.assertEqual(FiscalSetup.get().mode, "test")                  # not without typing LIVE
                self.client.post("/fiscal/setup/", {**form, "mode": "live", "sure": "LIVE"})
                self.assertEqual((FiscalSetup.get().mode, eng.read_config()["ZIMRASERVER"]),
                                 ("live", "https://fdmsapi.zimra.co.zw"))
                # the licence belongs to a serial number: Pondo writes serial + device ID into config.ini first
                self.client.post("/fiscal/setup/", {"do": "license", "license": "KEYXYZ", "serial": "HOYOTEST", "device": "38529"})
                cfg = eng.read_config()
                self.assertEqual((cfg["SERIALNUMBER"], cfg["DEVICEID"], cfg["LICENSEKEY"]), ("HOYOTEST", "38529", "KEYXYZ"))
                m = [c[0] for c in self.fake.calls]
                self.assertNotIn("SetLicense", m)          # SetLicense makes the engine lock its own folder
                self.assertEqual(m[-2:], ["restart", "CheckLicense"])
                self.assertEqual(eng._unprotect("ENC:abc") if __import__("sys").platform != "win32" else "", "")
                self.client.post("/fiscal/setup/", {"do": "register", "serial": "SN1", "activation": "KEY1", "device": "18084"})
                self.assertIn(("RegisterDeviceWithZimra", "KEY1", "SN1", "18084"), self.fake.calls)   # engine order
            finally:
                if pd is not None:
                    os.environ["PROGRAMDATA"] = pd


class EnvelopeTests(TestCase):
    def test_payload_reads_data_twice(self):
        self.assertEqual(eng.payload(env(1, "", {"a": 1})), {"a": 1})
        el = eng.payload(env(1, "", receipt_xml("X", 5)))
        self.assertEqual((eng.xml_text(el, "QRCode")[:8], eng.xml_text(el, "ReceiptGlobalNo")), ("https://", "5"))
        self.assertIsNone(eng.payload(env(1, "", "")))
        self.assertIsNone(eng.payload(env(1, "", "{not json")))

    def test_blocked_folder_answers_politely(self):
        from unittest import mock
        e = eng.Engine(folder=tempfile.mkdtemp())
        with mock.patch("fiscal.engine.os.listdir", side_effect=PermissionError("denied")), \
                mock.patch.object(Path, "exists", side_effect=PermissionError("denied")):
            self.assertFalse(e.installed())
            out = e.call("GetStatus")
        self.assertEqual(out["Code"], "0")
        self.assertIn("Windows is blocking", out["Message"])
        eng.set_engine(e)
        User.objects.create_superuser("boss", password="Boss-pass-1")
        FiscalSetup.objects.create(mode=FiscalSetup.TEST)
        self.client.login(username="boss", password="Boss-pass-1")
        with mock.patch("fiscal.engine.os.listdir", side_effect=PermissionError("denied")):
            for url in ("/fiscal/", "/fiscal/setup/"):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200, url)
                self.assertContains(r, "Windows is blocking")
        eng.set_engine(None)

    def test_missing_engine_answers_politely(self):
        e = eng.Engine(folder=tempfile.mkdtemp())
        out = e.call("GetStatus")
        self.assertEqual(out["Code"], "0")
        self.assertIn("not installed", out["Message"])


ENGINE = Path(settings.FISCAL_ENGINE_DIR)


@skipUnless((ENGINE / "PondoFiscalBridge.exe").exists() and (shutil.which("mono") or __import__("sys").platform == "win32"),
            "needs the real engine (Windows, or mono)")
class RealBridgeTests(TestCase):
    """Talks to the real FiscalStackZW.dll through the bridge. Without a licence every fiscal call must be refused
    with the engine's own message – and the sale must still be saved."""

    def setUp(self):
        self.e = eng.Engine()
        eng.set_engine(self.e)

    def tearDown(self):
        eng.set_engine(None)

    def test_license_gate_and_envelope(self):
        lic = self.e.call("CheckLicense")
        self.assertEqual(lic["Code"], "1", lic)
        data = eng.payload(lic)
        self.assertIn("allowed", data)
        self.assertIn("engineVersion", self.e.info)
        bad = self.e.call("NoSuchMethod", 1)
        self.assertEqual(bad["Code"], "0")
        self.assertTrue(self.e.running())      # one bad call doesn't kill the bridge
        if not data["allowed"]:
            out = self.e.call("TransactM", "USD", "", "TEST-1", "", "", "", "", "", "2.50", "0.34", "01", "", "",
                              "<ITEMS><ITEM><QTY>1</QTY><PRICE>2.50</PRICE><AMT>2.50</AMT><TAX>0.34</TAX><TAXR>0.155</TAXR></ITEM></ITEMS>",
                              service.currencies_xml(D("2.50")))
            self.assertEqual(out["Code"], "0")
            self.assertIn("License", out["Message"])
