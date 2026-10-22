"""Deliveries with a driver: invoice = goods + fee, the driver keeps the fee, money back is checked against the till."""
import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Access
from costing.models import Category, Recipe

from .models import Delivery, DocLine, Document


class DeliveryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(self.owner)
        cat = Category.objects.create(name="Cakes")
        self.cake = Recipe.objects.create(number=2001, name="Carrot cake", category=cat, sell_price=D("12.50"))
        self.pie = Recipe.objects.create(number=2002, name="Steak pie", category=cat, sell_price=D("2.00"))

    def post(self, url="/invoices/deliveries/new/", lines=(("Carrot cake", 2), ("Steak pie", 5)), **kw):
        data = {"c-name": "Tendai", "c-phone": "0772 000 111", "c-address1": "14 Fife Ave", "c-address2": "Avondale",
                "d-date": timezone.localdate().isoformat(), "d-driver_name": "Blessing", "d-driver_phone": "0783 111 222",
                "d-car_reg": "aez 1234", "d-car_make": "Honda Fit", "d-car_colour": "Silver", "d-fee": "3", "d-pay": "driver",
                "ln-TOTAL_FORMS": str(len(lines)), "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000"}
        for i, (n, q) in enumerate(lines):
            data[f"ln-{i}-product"], data[f"ln-{i}-qty"] = n, str(q)
        data.update(kw)
        return self.client.post(url, data)

    def test_cash_to_driver_flow(self):
        r = self.post()
        dl = Delivery.objects.get()
        self.assertRedirects(r, f"/invoices/deliveries/{dl.pk}/", fetch_redirect_response=False)
        self.assertEqual((dl.goods, dl.fee, dl.total, dl.expected_back, dl.car_reg), (D("35.00"), D("3"), D("38.00"), D("35.00"), "AEZ 1234"))
        doc = dl.doc
        self.assertEqual((doc.kind, doc.total, doc.status), (Document.INVOICE, D("38.00"), Document.OPEN))
        fee = doc.lines.get(is_fee=True)
        self.assertEqual((fee.price, fee.vat_rate), (D("3.00"), D("0")))
        self.assertIn("Blessing", fee.description)
        for url in ("/invoices/deliveries/", f"/invoices/deliveries/{dl.pk}/", f"/invoices/deliveries/{dl.pk}/note/",
                    f"/invoices/deliveries/{dl.pk}/edit/", f"/invoices/{doc.pk}/", "/excel/deliveries/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(f"/invoices/deliveries/{dl.pk}/note/"), "brings back to the bakery")
        self.assertContains(self.client.get("/"), "1 out with drivers · $35.00 to come back")
        self.assertRedirects(self.client.get(f"/invoices/{doc.pk}/edit/"), f"/invoices/deliveries/{dl.pk}/edit/",
                             fetch_redirect_response=False)
        # the driver brings back $1 short
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "delivered"})
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "back", "rung_up": "35", "till_ref": "T-12"})
        dl.refresh_from_db()
        self.assertEqual(dl.status, Delivery.OUT)  # money back must be typed
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "back", "money_back": "34", "rung_up": "35", "till_ref": "T-12"})
        dl.refresh_from_db()
        doc.refresh_from_db()
        self.assertEqual((dl.status, dl.difference, dl.till_ref), (Delivery.DONE, D("-1"), "T-12"))
        self.assertEqual((doc.status, doc.paid_how), (Document.PAID, "Cash via the driver"))
        # it shows on the cash-up of the day
        from sales.models import CashUp
        cu = CashUp.objects.create(date=timezone.localdate(), till="Main till")
        r = self.client.get(f"/sales/cashup/{cu.pk}/")
        self.assertContains(r, "Deliveries on the till")
        self.assertContains(r, "short $1.00")
        # open again
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "reopen"})
        dl.refresh_from_db()
        self.assertEqual((dl.status, dl.money_back), (Delivery.OUT, None))
        self.assertEqual(Document.objects.get(pk=doc.pk).status, Document.OPEN)

    def test_cash_only_and_cancel(self):
        self.post(**{"d-pay": "ecocash"})  # an old form can't make it anything but cash
        dl = Delivery.objects.get()
        self.assertEqual((dl.pay, dl.expected_back, dl.collect), (Delivery.DRIVER, D("35.00"), D("38.00")))
        self.assertIn("Cash on delivery", dl.doc.notes)
        self.assertContains(self.client.get(f"/invoices/deliveries/{dl.pk}/"), 'name="money_back"')
        self.assertContains(self.client.get(f"/invoices/deliveries/{dl.pk}/note/"), "Cash only")
        self.assertNotContains(self.client.get("/invoices/deliveries/new/"), 'name="d-pay"')
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "cancel"})
        dl.refresh_from_db()
        self.assertEqual((dl.status, dl.doc.status), (Delivery.CANCELLED, Document.CANCELLED))
        self.client.post(f"/invoices/{dl.doc.pk}/delete/")
        self.assertTrue(Document.objects.filter(pk=dl.doc.pk).exists())  # belongs to a delivery

    def test_from_quote_and_from_invoice(self):
        q = Document.objects.create(kind=Document.QUOTE, name="Hotel", phone="024 1")
        DocLine.objects.create(doc=q, recipe=self.cake, description="Carrot cake", qty=4, price=D("12.50"))
        q.refresh_totals()
        r = self.client.get(f"/invoices/deliveries/new/?from={q.pk}")
        self.assertContains(r, 'value="Carrot cake"')
        self.assertContains(r, 'value="Hotel"')
        self.post(url=f"/invoices/deliveries/new/?from={q.pk}", lines=(("Carrot cake", 4),), **{"c-name": "Hotel"})
        dl = Delivery.objects.get()
        self.assertEqual((dl.doc.kind, dl.doc.from_doc_id, dl.goods), (Document.INVOICE, q.pk, D("50.00")))
        q.refresh_from_db()
        self.assertEqual(q.status, Document.ACCEPTED)
        inv = Document.objects.create(kind=Document.INVOICE, name="Shop")
        DocLine.objects.create(doc=inv, recipe=self.pie, description="Steak pie", qty=10, price=D("2"))
        inv.refresh_totals()
        self.post(url=f"/invoices/deliveries/new/?from={inv.pk}", lines=(("Steak pie", 10),), **{"c-name": "Shop"})
        self.assertEqual(Delivery.objects.latest("id").doc_id, inv.pk)  # the same invoice, now with the fee
        self.assertEqual(Document.objects.get(pk=inv.pk).total, D("23.00"))
        self.assertRedirects(self.client.get(f"/invoices/deliveries/new/?from={inv.pk}"),
                             f"/invoices/deliveries/{Delivery.objects.latest('id').pk}/", fetch_redirect_response=False)

    def test_fee_must_be_typed_and_rights(self):
        r = self.post(**{"d-fee": ""})
        self.assertContains(r, "Type the delivery fee")
        self.assertFalse(Delivery.objects.exists())
        till = User.objects.create_user("till", password="x")
        Access.from_preset(till, "cashier")
        self.client.force_login(till)
        self.assertEqual(self.post().status_code, 302)
        self.assertEqual(Delivery.objects.count(), 1)
        baker = User.objects.create_user("bake", password="x")
        Access.from_preset(baker, "baker")
        self.client.force_login(baker)
        self.assertEqual(self.client.get("/invoices/deliveries/").status_code, 302)


class DriverTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path

        from django.test import override_settings

        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        ov = override_settings(STAFF_FILES_DIR=Path(self.tmp) / "staff_files")
        ov.enable()
        self.addCleanup(ov.disable)
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(self.owner)
        Recipe.objects.create(number=2001, name="Carrot cake", category=Category.objects.create(name="Cakes"),
                              sell_price=D("12.50"))

    def send(self, **kw):
        return DeliveryTests.post(self, lines=(("Carrot cake", 1),), **kw)

    def test_drivers_list_builds_itself_and_id_card(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .models import Driver

        self.send()
        drv = Driver.objects.get()
        self.assertEqual((drv.name, drv.car_reg, drv.number), ("Blessing", "AEZ 1234", "DRV-001"))
        self.assertEqual(Delivery.objects.get().driver, drv)
        # next time he is picked from the list – and comes with another car
        self.send(**{"d-driver": str(drv.pk), "d-car_reg": "ACD 9999", "d-car_colour": "Blue", "d-car_make": "Toyota Vitz"})
        self.assertEqual(Driver.objects.count(), 1)
        drv.refresh_from_db()
        self.assertEqual((drv.car_reg, drv.car_colour), ("ACD 9999", "Blue"))
        self.assertEqual(drv.deliveries.count(), 2)
        r = self.client.get(f"/invoices/deliveries/new/?driver={drv.pk}")
        self.assertContains(r, 'value="ACD 9999"')
        jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
        self.client.post(f"/invoices/drivers/{drv.pk}/photo/driver/change/", {"photo": SimpleUploadedFile("me.jpg", jpeg)})
        self.client.post(f"/invoices/drivers/{drv.pk}/photo/car/change/", {"photo": SimpleUploadedFile("car.jpg", jpeg)})
        drv.refresh_from_db()
        self.assertTrue(drv.photo.name.startswith(f"drivers/{drv.pk}/photo-"))
        self.assertTrue(drv.car_photo.name.startswith(f"drivers/{drv.pk}/car-"))
        self.assertEqual(self.client.get(f"/invoices/drivers/{drv.pk}/photo/driver/")["Content-Type"], "image/jpeg")
        self.client.post(f"/invoices/drivers/{drv.pk}/edit/", {"name": "Blessing Moyo", "phone": "0783 111 222",
                                                               "id_number": "63-123456 a 42", "licence_no": "",
                                                               "car_reg": "ACD 9999", "car_make": "Toyota Vitz",
                                                               "car_colour": "Blue", "issued": "2026-10-09", "active": "on"})
        drv.refresh_from_db()
        self.assertEqual(drv.id_number, "63-123456 A 42")
        for url in ("/invoices/drivers/", f"/invoices/drivers/{drv.pk}/", "/invoices/drivers/new/", "/invoices/drivers/cards/",
                    "/excel/drivers/", "/excel/deliveries/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        card = self.client.get(f"/invoices/drivers/{drv.pk}/card/")
        for text in ("Blessing Moyo", "DRV-001", "63-123456 A 42", "ACD 9999", "Cash only", f"/invoices/drivers/{drv.pk}/photo/car/"):
            self.assertContains(card, text)
        dl = Delivery.objects.latest("id")
        self.assertContains(self.client.get(f"/invoices/deliveries/{dl.pk}/note/"), f"/invoices/drivers/{drv.pk}/photo/driver/")
        # money short shows on the driver
        self.client.post(f"/invoices/deliveries/{dl.pk}/status/", {"to": "back", "money_back": "10", "rung_up": "12.50"})
        self.assertContains(self.client.get("/invoices/drivers/"), "short $2.50")
        # a baker may not see drivers or their photos
        baker = User.objects.create_user("bake", password="x")
        Access.from_preset(baker, "baker")
        self.client.force_login(baker)
        self.assertEqual(self.client.get(f"/invoices/drivers/{drv.pk}/photo/driver/").status_code, 302)
        self.assertEqual(self.client.get("/invoices/drivers/").status_code, 302)
