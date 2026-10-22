import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Access
from costing.models import Ingredient, Recipe, RecipeLine

from .models import CashUp, DaySales, Expense, ExpenseCategory, PaymentMethod
from .report import month_report


class SalesTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.cash = PaymentMethod.objects.get(name="Cash (US$)")
        self.card = PaymentMethod.objects.get(name="Swipe / card")
        self.gas = ExpenseCategory.objects.get(name="Gas & fuel")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("1"))
        self.loaf = Recipe.objects.create(number=1, name="Loaf", scaling_weight=D("0.5"), sell_price=D("1.15"),
                                          vat_rate=D("0"))
        RecipeLine.objects.create(recipe=self.loaf, ingredient=flour, qty=10)  # 20 loaves, $0.50 each

    def post_cashup(self, cu, **extra):
        data = {"cashier": "Rudo", "opening_float": "50", "cash_counted": "650", "float_left": "50", "banked": "600",
                "notes": "", f"till_{self.cash.pk}": "600", f"till_{self.card.pk}": "300", f"actual_{self.card.pk}": "295",
                "po-TOTAL_FORMS": "2", "po-INITIAL_FORMS": "0", "po-MIN_NUM_FORMS": "0", "po-MAX_NUM_FORMS": "1000",
                "po-0-category": str(self.gas.pk), "po-0-payee": "Gas man", "po-0-description": "LP gas", "po-0-amount": "20",
                "po-1-category": "", "po-1-amount": ""}
        data.update(extra)
        return self.client.post(f"/sales/cashup/{cu.pk}/edit/", data)

    def test_cashup_maths_and_flow(self):
        r = self.client.post("/sales/cashup/new/", {"date": "2026-10-09", "till": "Till 1"})
        cu = CashUp.objects.get()
        self.assertRedirects(r, f"/sales/cashup/{cu.pk}/edit/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(f"/sales/cashup/{cu.pk}/edit/").status_code, 200)
        self.assertEqual(self.post_cashup(cu).status_code, 302)
        cu.refresh_from_db()
        res = cu.result()
        self.assertEqual(res["cash_taken"], D("620"))      # 650 − 50 + 20 paid out
        self.assertEqual(res["cash_variance"], D("20"))    # over
        self.assertEqual(res["variance"], D("15.00"))      # +20 cash, −5 card
        self.assertEqual((cu.total_sales, cu.total_variance), (D("900"), D("15.00")))
        self.assertEqual(res["to_bank"], D("600"))
        self.assertEqual(Expense.objects.get().paid_from, "till")
        for url in (f"/sales/cashup/{cu.pk}/", f"/sales/cashup/{cu.pk}/print/", "/sales/", "/sales/expenses/?month=2026-10"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        # same till same day refused
        r = self.client.post("/sales/cashup/new/", {"date": "2026-10-09", "till": "Till 1"})
        self.assertContains(r, "already a cash-up")
        # next day's float comes from today's float left
        self.client.post("/sales/cashup/new/", {"date": "2026-10-10", "till": "Till 1"})
        self.assertEqual(CashUp.objects.get(date="2026-10-10").opening_float, D("50"))

    def test_zig_cash(self):
        self.client.post("/sales/cashup/new/", {"date": "2026-10-09", "till": "Till 1"})
        cu = CashUp.objects.get()
        r = self.post_cashup(cu, cash_counted="600", zig_counted="2700", zig_rate="")
        self.assertContains(r, "Type the ZiG rate")
        self.post_cashup(cu, cash_counted="600", zig_counted="2700", zig_rate="27")
        cu.refresh_from_db()
        res = cu.result()
        self.assertEqual((res["zig_usd"], res["cash_taken"], res["cash_variance"]), (D("100.00"), D("670.00"), D("70.00")))
        self.client.post("/sales/cashup/new/", {"date": "2026-10-10", "till": "Till 1"})
        self.assertEqual(CashUp.objects.get(date="2026-10-10").zig_rate, D("27"))  # the rate is remembered

    def test_signoff_locks_for_managers(self):
        mgr = User.objects.create_user("mgr", password="TestPass123!")
        Access.from_preset(mgr, "supervisor")
        cash = User.objects.create_user("till", password="TestPass123!")
        Access.from_preset(cash, "cashier")
        cu = CashUp.objects.create(date="2026-10-09", created_by=cash)
        self.client.logout()
        self.client.login(username="till", password="TestPass123!")
        self.assertEqual(self.client.get("/sales/").status_code, 200)
        self.client.post(f"/sales/cashup/{cu.pk}/signoff/")
        cu.refresh_from_db()
        self.assertIsNone(cu.signed_off_by)  # a cashier can't sign off
        self.assertRedirects(self.client.get("/sales/report/"), "/", fetch_redirect_response=False)  # no costs
        self.client.logout()
        self.client.login(username="mgr", password="TestPass123!")
        self.client.post(f"/sales/cashup/{cu.pk}/signoff/")
        cu.refresh_from_db()
        self.assertEqual(cu.signed_off_by, mgr)
        self.assertRedirects(self.client.get(f"/sales/cashup/{cu.pk}/edit/"), f"/sales/cashup/{cu.pk}/", fetch_redirect_response=False)

    def test_expenses_product_sales_and_report(self):
        r = self.client.post("/sales/expenses/new/", {"date": "2026-10-03", "category": self.gas.pk, "amount": "45",
                                                      "paid_from": "bank", "payee": "", "description": "", "receipt_no": ""})
        self.assertEqual(r.status_code, 302)
        cu = CashUp.objects.create(date="2026-10-09")
        self.post_cashup(cu)
        r = self.client.post("/sales/products/new/", {"date": "2026-10-09", "start": "all"})
        day = DaySales.objects.get()
        self.assertIn("?all=1", r["Location"])
        page = self.client.get(r["Location"])
        self.assertContains(page, 'value="Loaf"')
        data = {"notes": "", "ln-TOTAL_FORMS": "2", "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000",
                "ln-0-product": "loaf", "ln-0-qty": "100", "ln-0-price": "", "ln-1-product": "", "ln-1-qty": ""}
        self.assertEqual(self.client.post(f"/sales/products/{day.pk}/edit/", data).status_code, 302)
        t = day.totals()
        self.assertEqual((t["value"], t["cost"]), (D("115.00"), D("50")))
        self.assertEqual(self.client.get(f"/sales/products/{day.pk}/").status_code, 200)
        rep = month_report(datetime.date(2026, 10, 1))
        self.assertEqual(rep["taken"], D("900"))
        self.assertEqual(rep["expenses"], D("65"))   # 45 bank + 20 out of the till
        self.assertEqual(rep["total"], D("0"))       # sales come from Daily sales, none typed here
        for url in ("/sales/report/?month=2026-10", "/sales/products/", "/sales/setup/", "/sales/setup/method/new/",
                    f"/sales/setup/category/{self.gas.pk}/", "/", "/production/waste/summary/?month=2026-10"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
