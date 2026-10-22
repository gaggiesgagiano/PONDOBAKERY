from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from costing.models import Ingredient, IngredientPriceChange, Recipe, RecipeLine, Supplier
from production.models import PlanLine, ProductionPlan

from .levels import on_hand_all
from .models import GRV, PurchaseOrder, StockCount

MGMT = {"ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000"}


class StockTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.sup = Supplier.objects.create(name="Aries")
        self.flour = Ingredient.objects.create(name="Flour 25kg", unit="kg", pack_size=25, pack_price=D("20"),
                                               supplier=self.sup, reorder_level=50, stock_par=100)
        self.loaf = Recipe.objects.create(number=1, name="Loaf", scaling_weight=D("0.5"), sell_price=D("2"))
        RecipeLine.objects.create(recipe=self.loaf, ingredient=self.flour, qty=10)

    def test_order_suggest_receive_and_price_update(self):
        page = self.client.get(f"/stock/orders/new/?supplier={self.sup.pk}")
        self.assertContains(page, "Flour 25kg")                # low -> suggested
        r = self.client.post("/stock/orders/new/", {"supplier": self.sup.pk, "date": "2026-10-09", "delivery_date": "", "notes": "",
                                                    "ln-TOTAL_FORMS": "1", **MGMT, "ln-0-item": "flour 25kg", "ln-0-packs": "4", "ln-0-pack_price": ""})
        o = PurchaseOrder.objects.get()
        self.assertEqual(o.lines.get().pack_price, D("20"))
        self.assertEqual(o.total, D("80"))
        for url in (f"/stock/orders/{o.pk}/", f"/stock/orders/{o.pk}/print/", f"/stock/grv/new/?order={o.pk}"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post(f"/stock/grv/new/?order={o.pk}", {"supplier": self.sup.pk, "date": "2026-10-10", "invoice_no": "INV1",
                                                               "invoice_total": "", "notes": "", "update_prices": "on",
                                                               "ln-TOTAL_FORMS": "1", **MGMT, "ln-0-item": "Flour 25kg",
                                                               "ln-0-packs_ordered": "4", "ln-0-packs": "3", "ln-0-pack_price": "22"})
        g = GRV.objects.get()
        self.assertRedirects(r, f"/stock/grv/{g.pk}/", fetch_redirect_response=False)
        o.refresh_from_db(); self.flour.refresh_from_db()
        self.assertEqual(o.status, "received")
        self.assertEqual(self.flour.pack_price, D("22"))
        self.assertTrue(IngredientPriceChange.objects.filter(ingredient=self.flour, new_price=D("22")).exists())
        self.assertEqual(on_hand_all()[0][self.flour.pk], D("75"))
        self.assertContains(self.client.get(f"/stock/grv/{g.pk}/"), "-1")    # one pack short

    def finalise(self, c):
        return self.client.post(f"/stock/counts/{c.pk}/variance/", {"finalise": "1"})

    def test_count_usage_and_cogs(self):
        from core.models import CompanySettings
        cs = CompanySettings.get(); cs.stock_usage = "production"; cs.save()
        c = StockCount.objects.create(date="2026-10-01")
        self.client.post(f"/stock/counts/{c.pk}/edit/", {"date": "2026-10-01", "counted_by": "", "checked_by": "", "notes": "",
                                                        f"q_i_{self.flour.pk}": "100"})
        self.finalise(c)
        c.refresh_from_db()
        self.assertEqual((c.status, c.total_value), ("final", D("80.00")))
        # deliver 2 bags, bake 1 batch (10 kg)
        self.client.post("/stock/grv/new/", {"supplier": self.sup.pk, "date": "2026-10-03", "invoice_no": "", "invoice_total": "",
                                            "notes": "", "ln-TOTAL_FORMS": "1", **MGMT, "ln-0-item": "Flour 25kg",
                                            "ln-0-packs_ordered": "", "ln-0-packs": "2", "ln-0-pack_price": "20"})
        plan = ProductionPlan.objects.create(date="2026-10-04", shift="day")
        PlanLine.objects.create(plan=plan, recipe=self.loaf, actual=20)
        self.client.post(f"/production/{plan.pk}/status/", {"status": "done"})
        self.assertEqual(on_hand_all()[0][self.flour.pk], D("140"))          # 100 + 50 - 10
        page = self.client.get("/stock/")
        self.assertContains(page, "140")
        # second count -> COGS = 80 + 40 - closing
        self.client.post("/stock/counts/new/")
        c2 = StockCount.objects.filter(status="draft").get()
        self.client.post(f"/stock/counts/{c2.pk}/edit/", {"date": "2026-10-08", "counted_by": "", "checked_by": "", "notes": "",
                                                         f"q_i_{self.flour.pk}": "125"})
        self.finalise(c2)
        c2.refresh_from_db()
        self.assertEqual(c2.total_value, D("100.00"))
        lst = self.client.get("/stock/counts/")
        self.assertContains(lst, "$20.00")                                    # 80 + 40 - 100
        det = self.client.get(f"/stock/counts/{c2.pk}/")
        self.assertContains(det, "-15")                                       # expected 140, counted 125
        self.assertEqual(self.client.get(f"/stock/counts/{c2.pk}/sheet/").status_code, 200)


class StockFromSalesTests(TestCase):
    """GRV adds stock, till sales and waste take it off, blind count, variance, reasons, only a manager finalises."""

    def setUp(self):
        import datetime
        from core.models import Access
        from production.models import WasteLine, WasteLog
        from sales.models import PaymentMethod
        from till.models import Sale, SaleItem, SalePayment, Shift, Till
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.sup_user = User.objects.create_user("sid", password="Sid-pass-1")
        Access.from_preset(self.sup_user, "supervisor")
        self.supplier = Supplier.objects.create(name="Aries")
        self.flour = Ingredient.objects.create(name="Cake flour", unit="kg", pack_size=25, pack_price=D("20"), supplier=self.supplier)
        self.loaf = Recipe.objects.create(number=1, name="Loaf", scaling_weight=D("0.5"), sell_price=D("2"))
        RecipeLine.objects.create(recipe=self.loaf, ingredient=self.flour, qty=10)     # 20 loaves -> 0.5 kg flour each
        self.client.login(username="owner", password="TestPass123!")
        self.client.post("/stock/grv/new/", {"supplier": self.supplier.pk, "date": "2026-10-03", "invoice_no": "", "invoice_total": "",
                                            "notes": "", "ln-TOTAL_FORMS": "1", **MGMT, "ln-0-item": "Cake flour",
                                            "ln-0-packs_ordered": "", "ln-0-packs": "4", "ln-0-pack_price": "20"})   # 100 kg
        sh = Shift.objects.create(till=Till.objects.get(name="Till 1"), date=datetime.date(2026, 10, 4), cashier=self.owner)
        s = Sale.objects.create(shift=sh, number="T1-1", total=D("8"))
        SaleItem.objects.create(sale=s, recipe=self.loaf, name="Loaf", qty=4, price=2, total=8)           # 2 kg
        SalePayment.objects.create(sale=s, method=PaymentMethod.objects.first(), amount=8)
        log = WasteLog.objects.create(date=datetime.date(2026, 10, 4))
        WasteLine.objects.create(log=log, recipe=self.loaf, qty=2)                                         # 1 kg

    def test_flow(self):
        self.assertEqual(on_hand_all()[0][self.flour.pk], D("97"))
        self.client.post("/stock/counts/new/")
        c = StockCount.objects.get()
        sheet = self.client.get(f"/stock/counts/{c.pk}/sheet/")
        self.assertContains(sheet, "Cake flour")
        self.assertNotContains(sheet, "97")                     # count sheets print empty
        var = self.client.get(f"/stock/counts/{c.pk}/variance/")
        self.assertContains(var, "not counted")
        self.finalise_blocked(c, "not counted yet")
        self.client.post(f"/stock/counts/{c.pk}/edit/", {"date": "2026-10-08", "counted_by": "", "checked_by": "", "notes": "",
                                                        f"q_i_{self.flour.pk}": "-1"})
        self.client.post(f"/stock/counts/{c.pk}/edit/", {"date": "2026-10-08", "counted_by": "", "checked_by": "", "notes": "",
                                                        f"q_i_{self.flour.pk}": "47", "go": "variance"})
        r = self.client.get(f"/stock/counts/{c.pk}/variance/")
        self.assertContains(r, "-50")                            # 47 counted vs 97 expected
        self.assertContains(r, "$40.00")                         # 50 kg x $0.80
        edit = self.client.get(f"/stock/counts/{c.pk}/edit/?diff=1")
        self.assertContains(edit, "Cake flour")
        # a supervisor may not finalise
        self.client.login(username="sid", password="Sid-pass-1")
        self.client.post(f"/stock/counts/{c.pk}/variance/", {"finalise": "1"})
        self.assertEqual(StockCount.objects.get().status, "draft")
        # difference of $40 with the limit at $20 needs a reason
        self.client.login(username="owner", password="TestPass123!")
        from core.models import CompanySettings
        cs = CompanySettings.get(); cs.stock_variance_limit = D("20"); cs.save()
        self.finalise_blocked(c, "Explain every difference")
        self.client.post(f"/stock/counts/{c.pk}/variance/", {f"r_{self.flour.pk}": "Bag torn, 50 kg thrown away", "finalise": "1"})
        c.refresh_from_db()
        self.assertEqual((c.status, c.finalized_by, c.total_value), ("final", self.owner, D("37.60")))
        self.assertEqual(c.lines.get(ingredient=self.flour).reason, "Bag torn, 50 kg thrown away")
        self.assertEqual(on_hand_all()[0][self.flour.pk], D("47"))
        self.assertContains(self.client.get(f"/stock/counts/{c.pk}/variance/"), "Bag torn")

    def finalise_blocked(self, c, text):
        r = self.client.post(f"/stock/counts/{c.pk}/variance/", {"finalise": "1"}, follow=True)
        self.assertContains(r, text)
        self.assertEqual(StockCount.objects.get(pk=c.pk).status, "draft")
