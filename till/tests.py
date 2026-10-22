import json
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Access, ChangeLog, CompanySettings
from costing.models import Category, Ingredient, Recipe, RecipeLine
from sales.models import CashUp, DailySales, DaySales, PaymentMethod

from .models import Sale, Shift, Till


class TillTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("boss", password="Boss-pass-1")
        self.cashier = User.objects.create_user("rudo", password="Rudo-pass-1", first_name="Rudo")
        Access.from_preset(self.cashier, "cashier")
        self.sup = User.objects.create_user("sid", password="Sid-pass-1")
        Access.from_preset(self.sup, "supervisor")
        cat = Category.objects.create(name="Pies")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("1"))
        self.pie = Recipe.objects.create(number=201254, name="Pondo Cheeseburger Pie", scaling_weight=D("0.5"),
                                         sell_price=D("2.50"), vat_rate=D("0.155"), category=cat)
        RecipeLine.objects.create(recipe=self.pie, ingredient=flour, qty=10)
        self.cash = PaymentMethod.objects.get(name="Cash (US$)")
        self.eco = PaymentMethod.objects.get(name="EcoCash")
        self.till = Till.objects.get(name="Till 1")
        cs = CompanySettings.get()
        cs.zwg_rate = D("26.5")       # ZWG per US$1 – set by the Manager in Settings
        cs.save()

    def open_till(self):
        self.client.login(username="rudo", password="Rudo-pass-1")
        r = self.client.post("/till/", {"till": self.till.pk, "float": "200", "zig_rate": "26.5"})
        sh = Shift.objects.get()
        self.assertRedirects(r, f"/till/{sh.pk}/", fetch_redirect_response=False)
        return sh

    def sell(self, sh, items, payments):
        return self.client.post(f"/till/{sh.pk}/sell/", json.dumps({"items": items, "payments": payments}),
                                content_type="application/json")

    def test_full_day(self):
        sh = self.open_till()
        self.assertEqual(self.client.get(f"/till/{sh.pk}/").status_code, 200)
        # cash with change
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 3}], [{"method": self.cash.pk, "amount": "10"}]).json()
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["total"], r["change"]), ("7.50", "2.50"))
        sale = Sale.objects.get(number=r["number"])
        self.assertEqual(sale.payments.get().amount, D("7.50"))
        self.assertEqual(self.client.get(r["receipt"]).status_code, 200)
        # EcoCash needs a reference, can't be more than the total
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.eco.pk, "amount": "2.50"}]).json()
        self.assertFalse(r["ok"])
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.eco.pk, "amount": "5", "ref": "X1"}]).json()
        self.assertFalse(r["ok"])
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 2}], [{"method": self.eco.pk, "amount": "3", "ref": "PP123"},
                                                           {"method": self.cash.pk, "zig": "53"}]).json()
        self.assertTrue(r["ok"], r)       # $3 EcoCash + ZiG 53 (= $2) for $5
        # short payment refused
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 2}], [{"method": self.cash.pk, "amount": "4"}]).json()
        self.assertFalse(r["ok"])
        # refund: cashier can't approve, supervisor can up to $5, more needs a manager
        url = f"/till/{sh.pk}/refund/{sale.pk}/"
        item = sale.items.get()
        base = {f"q{item.pk}": "1", "reason": "wrong product", "method": self.cash.pk}
        r = self.client.post(url, {**base, "by": "rudo", "pw": "Rudo-pass-1"})
        self.assertContains(r, "can&#x27;t approve their own")
        r = self.client.post(url, {**base, f"q{item.pk}": "3", "by": "sid", "pw": "Sid-pass-1"})
        self.assertContains(r, "need a manager")
        r = self.client.post(url, {**base, "by": "sid", "pw": "Sid-pass-1"})
        self.assertEqual(r.status_code, 302)
        rf = Sale.objects.get(kind="refund")
        self.assertEqual(rf.total, D("-2.50"))
        r = self.client.post(url, {**base, f"q{item.pk}": "3", "by": "boss", "pw": "Boss-pass-1"})
        self.assertContains(r, "at most 2")
        self.assertEqual(self.client.get(f"/till/{sh.pk}/sales/").status_code, 200)
        # close: makes the cash-up and the day's sales
        self.assertEqual(self.client.get(f"/till/{sh.pk}/close/").status_code, 200)
        r = self.client.post(f"/till/{sh.pk}/close/", {"cash": "205", "zig": "53", "float_left": "200"})
        cu = CashUp.objects.get()
        self.assertRedirects(r, f"/sales/cashup/{cu.pk}/?saved=1", fetch_redirect_response=False)
        lines = {ln.method.name: ln.till_amount for ln in cu.lines.all()}
        self.assertEqual(lines["Cash (US$)"], D("7.00"))     # 7.50 + 2.00 ZiG − 2.50 refund
        self.assertEqual(lines["EcoCash"], D("3.00"))
        res = cu.result()
        self.assertEqual(res["cash_variance"], D("0.00"))     # 205 + 2 (ZiG) − 200 = 7
        ds = DaySales.objects.get(date=timezone.localdate())
        self.assertEqual(ds.lines.get().qty, D("4"))          # 3 + 2 − 1
        self.assertEqual(DailySales.objects.get().total, D("8.66"))   # $10 incl. 15.5% VAT
        self.assertFalse(Shift.objects.get().is_open)
        self.assertEqual(self.client.get(f"/till/{sh.pk}/").status_code, 302)

    def test_rights(self):
        baker = User.objects.create_user("baker", password="Baker-pass-1")
        Access.from_preset(baker, "baker")
        self.client.login(username="baker", password="Baker-pass-1")
        self.assertEqual(self.client.get("/till/").status_code, 302)
        sh = self.open_till()
        self.client.login(username="sid", password="Sid-pass-1")
        self.assertEqual(self.client.get(f"/till/{sh.pk}/").status_code, 404)   # not his till
        r = self.client.post("/till/", {"till": self.till.pk, "float": "200"})
        self.assertEqual(Shift.objects.count(), 1)


class TillShiftTests(TestCase):
    """Two shifts on one till, cash drop / pay-out / no sale with approval, refund to waste."""

    def setUp(self):
        TillTests.setUp(self)
        self.mgr = User.objects.create_user("am", password="Am-pass-1")
        Access.from_preset(self.mgr, "assistant_manager")
        self.cash2 = User.objects.create_user("tendai", password="Tendai-pass-1", first_name="Tendai")
        Access.from_preset(self.cash2, "cashier")

    open_till = TillTests.open_till
    sell = TillTests.sell

    def test_shifts_moves_and_waste(self):
        from production.models import WasteLine
        from sales.models import Expense, ExpenseCategory
        from .models import TillMovement
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 160}], [{"method": self.cash.pk, "amount": "400"}]).json()
        self.assertEqual(r["drawer"], "600.00")                        # 200 float + 400
        self.assertContains(self.client.get(f"/till/{sh.pk}/"), "call the manager for a cash drop")
        url = f"/till/{sh.pk}/move/drop/"
        self.assertContains(self.client.post(url, {"amount": "300", "by": "sid", "pw": "Sid-pass-1"}), "Only a manager")
        r = self.client.post(url, {"amount": "300", "by": "am", "pw": "Am-pass-1"})
        mv = TillMovement.objects.get(kind="drop")
        self.assertRedirects(r, f"/till/slip/{mv.pk}/?print=1&back=/till/{sh.pk}/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(f"/till/slip/{mv.pk}/").status_code, 200)
        gas = ExpenseCategory.objects.first()
        r = self.client.post(f"/till/{sh.pk}/move/payout/", {"amount": "20", "category": gas.pk, "reason": "LP gas", "payee": "Gas man",
                                                             "by": "rudo", "pw": "Rudo-pass-1"})
        self.assertContains(r, "approve for their own till")
        self.client.post(f"/till/{sh.pk}/move/payout/", {"amount": "20", "category": gas.pk, "reason": "LP gas", "by": "sid", "pw": "Sid-pass-1"})
        self.client.post(f"/till/{sh.pk}/move/nosale/", {"reason": "change for a $50", "by": "sid", "pw": "Sid-pass-1"})
        self.assertEqual(TillMovement.objects.count(), 3)
        # refund one pie to waste
        sale = Sale.objects.get()
        self.client.post(f"/till/{sh.pk}/refund/{sale.pk}/", {f"q{sale.items.get().pk}": "1", "reason": "dropped", "method": self.cash.pk,
                                                              "waste": "1", "by": "sid", "pw": "Sid-pass-1"})
        self.assertEqual(WasteLine.objects.get().reason, "Customer return")
        # close shift 1: 600 − 300 drop − 20 pay-out − 2.50 refund = 277.50 in the drawer
        self.client.post(f"/till/{sh.pk}/close/", {"cash": "277.50", "zig": "", "float_left": "200"})
        cu = CashUp.objects.get(till="Till 1")
        self.assertEqual((cu.drops, cu.result()["cash_variance"]), (D("300.00"), D("0.00")))
        self.assertEqual(Expense.objects.get().cashup, cu)
        # shift 2 re-opens Till 1 with a fresh float and gets its own cash-up
        self.client.login(username="tendai", password="Tendai-pass-1")
        self.client.post("/till/", {"till": self.till.pk, "float": "200", "zig_rate": "26.5"})
        sh2 = Shift.objects.get(number=2)
        self.assertEqual(sh2.label, "Till 1 #2")
        r = self.sell(sh2, [{"id": self.pie.pk, "qty": 2}], [{"method": self.cash.pk, "amount": "5"}]).json()
        self.assertTrue(r["ok"])
        self.client.post(f"/till/{sh2.pk}/close/", {"cash": "205", "zig": "", "float_left": "200"})
        self.assertEqual(CashUp.objects.get(till="Till 1 #2").result()["cash_variance"], D("0.00"))
        self.assertEqual(self.client.get("/till/").status_code, 200)


class ZwgPaymentTests(TestCase):
    """Currency first (USD / ZWG), then how; the rate comes from Settings and applies to every sale at once."""

    def setUp(self):
        TillTests.setUp(self)

    open_till = TillTests.open_till
    sell = TillTests.sell

    def test_zwg_by_any_method_at_the_settings_rate(self):
        sh = self.open_till()
        self.assertEqual(sh.zig_rate, D("26.5"))          # no rate typed when opening the till
        page = self.client.get(f"/till/{sh.pk}/")
        self.assertContains(page, 'data-c="ZWG"')
        self.assertContains(page, "ZWG 26.50/$1")
        names = [m["name"] for m in json.loads(page.context["methods_json"])]
        self.assertIn("Cash", names)                        # "Cash (US$)" shows as "Cash" – the currency is picked first
        # $5 sale: ZWG 66.25 by EcoCash (= $2.50) + ZWG 66.25 cash
        r = self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "26.5", "items": [{"id": self.pie.pk, "qty": 2}],
            "payments": [{"method": self.eco.pk, "zig": "66.25", "ref": "MP1"}, {"method": self.cash.pk, "zig": "66.25"}]}),
            content_type="application/json").json()
        self.assertTrue(r["ok"], r)
        sale = Sale.objects.get(number=r["number"])
        eco = sale.payments.get(method=self.eco)
        self.assertEqual((eco.amount, eco.zig_amount, eco.zig_rate), (D("2.50"), D("66.25"), D("26.5")))
        # "exact" in ZWG rounds up a cent: a card payment is capped at what is due, not refused
        r = self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "26.5", "items": [{"id": self.pie.pk, "qty": 1}],
            "payments": [{"method": self.eco.pk, "zig": "66.26", "ref": "MP2"}]}), content_type="application/json").json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(Sale.objects.get(number=r["number"]).payments.get().amount, D("2.50"))
        # the Manager changes the rate: the open till uses it at once; a payment typed at the old rate is refused
        self.client.login(username="boss", password="Boss-pass-1")
        form = {f"c-{k}": v for k, v in {"company_name": "Pondo Bakery", "vat_percent": "15.5", "target_percent": "60",
                                         "low_percent": "35", "zwg_rate": "27"}.items()}
        form.update({"s-name": "Pondo Bakery"})
        self.client.post("/settings/", form)
        self.assertEqual(CompanySettings.get().zwg_rate, D("27"))
        self.assertIn("→ 27", ChangeLog.objects.get(item="ZWG rate").details)
        self.client.login(username="rudo", password="Rudo-pass-1")
        r = self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "26.5", "items": [{"id": self.pie.pk, "qty": 1}],
            "payments": [{"method": self.cash.pk, "zig": "66.25"}]}), content_type="application/json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["rate"], "27.0000")
        r = self.client.post(f"/till/{sh.pk}/sell/", json.dumps({
            "rate": "27", "items": [{"id": self.pie.pk, "qty": 1}],
            "payments": [{"method": self.cash.pk, "zig": "67.50"}]}), content_type="application/json").json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(Sale.objects.get(number=r["number"]).payments.get().zig_rate, D("27"))
        # cash-up: only ZWG *cash* is in the drawer, counted at the latest rate
        self.assertContains(self.client.get(f"/till/{sh.pk}/close/"), "ZWG")
        self.client.post(f"/till/{sh.pk}/close/", {"cash": "200", "zig": "133.75", "float_left": "200"})
        cu = CashUp.objects.get()
        self.assertEqual((cu.zig_counted, cu.zig_rate), (D("133.75"), D("27")))

    def test_no_rate_means_usd_only(self):
        cs = CompanySettings.get()
        cs.zwg_rate = None
        cs.save()
        sh = self.open_till()
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "zig": "30"}]).json()
        self.assertFalse(r["ok"])
        self.assertIn("Settings", r["error"])
        r = self.sell(sh, [{"id": self.pie.pk, "qty": 1}], [{"method": self.cash.pk, "amount": "2.50"}]).json()
        self.assertTrue(r["ok"])
