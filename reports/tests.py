import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Overhead
from costing.models import Ingredient, Supplier
from sales.models import DailySales, Expense, ExpenseCategory
from staff.models import Employee
from stock.models import GRV, GRVLine, StockCount

from .calc import month_end, stock_results
from .models import MonthClose

OCT = datetime.date(2026, 10, 1)


class ReportTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        sup = Supplier.objects.create(name="Aries")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=25, pack_price=D("230"), vat_rate=D("0.15"), supplier=sup)
        StockCount.objects.create(date="2026-09-30", status="final", total_value=D("5000"))
        StockCount.objects.create(date="2026-10-31", status="final", total_value=D("4000"))
        g = GRV.objects.create(supplier=sup, date="2026-10-15")
        GRVLine.objects.create(grv=g, ingredient=flour, packs=10, pack_price=D("230"))  # 2300 incl. = 2000 excl.
        DailySales.objects.create(date="2026-10-05", total=D("8000"), gp_amount=D("5000"))
        Employee.objects.create(first_name="Ann", rate=D("1000"))
        Overhead.objects.create(name="Rent", monthly_cost=D("1500"))
        rent = ExpenseCategory.objects.get_or_create(name="Rent")[0]
        casual = ExpenseCategory.objects.get(name="Casual wages & overtime")
        Expense.objects.create(date="2026-10-01", category=rent, amount=D("1150"), vat=D("150"))
        Expense.objects.create(date="2026-10-20", category=casual, amount=D("200"))

    def test_month_end_profit_and_loss(self):
        m = month_end(OCT)
        self.assertEqual(m["cos_from"], "stock")
        self.assertEqual((m["purchases"], m["cos"], m["gross"]), (D("2000"), D("3000"), D("5000")))
        self.assertEqual((m["wages_from"], m["wages"]), ("staff", D("1000")))
        self.assertEqual((m["running_from"], m["running"], m["casual"]), ("actual", D("1000"), D("200")))
        self.assertEqual(m["net"], D("2800"))
        self.assertEqual(m["vs_target"], D("2800") - D("15000"))
        self.assertEqual(m["vat_expenses"], D("150"))
        self.assertEqual(m["running_vs_budget"], D("500"))
        self.assertEqual(m["stock_change"], D("-1000"))

    def test_stock_results(self):
        r = stock_results(OCT)
        self.assertEqual(len(r["periods"]), 1)
        p = r["periods"][0]
        self.assertEqual((p["cos"], p["gp"], p["gp_pct"]), (D("3000"), D("5000"), D("0.625")))
        self.assertEqual(p["unexplained"], D("0"))
        self.assertEqual(r["by_supplier"], [("Aries", D("2000"))])

    def test_no_stock_takes_uses_recipes_and_budget(self):
        StockCount.objects.all().delete()
        Expense.objects.all().delete()
        m = month_end(OCT)
        self.assertEqual((m["cos_from"], m["cos"]), ("recipes", D("3000")))
        self.assertEqual((m["running_from"], m["running"]), ("budget", D("1500")))

    def test_pages_and_lock(self):
        for url in ("/reports/?month=2026-10", "/reports/stock/?month=2026-10", "/reports/archive/", "/reports/", "/sales/report/?month=2026-10"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get("/reports/?month=2026-10"), "$2,800.00")
        r = self.client.post("/reports/archive/lock/", {"month": "2026-10-01"})
        self.assertRedirects(r, "/reports/?month=2026-10", fetch_redirect_response=False)
        mc = MonthClose.objects.get()
        self.assertEqual(mc.figures["net"], "2800.00")
        self.assertContains(self.client.get("/reports/archive/"), "Oct 2026")
        self.client.post(f"/reports/archive/{mc.pk}/", {"sent_to_accountant": "02 Nov JG"})
        mc.refresh_from_db()
        self.assertEqual(mc.sent_to_accountant, "02 Nov JG")

    def test_one_page_prints(self):
        from sales.models import CashUp
        CashUp.objects.create(date="2026-10-05", till="Main till")
        r = self.client.get("/reports/print/?month=2026-10")
        self.assertContains(r, "Month-end report")
        self.assertContains(r, "$2,800.00")
        self.assertContains(r, 'id="fit"')
        self.assertEqual(month_end(OCT)["vat_days"], 1)
        r = self.client.get("/print/dashboard/?date=2026-10-05")
        self.assertContains(r, "Daily dashboard")
        self.assertContains(r, "Mon 05 Oct 2026")
        self.assertEqual(self.client.get("/print/dashboard/?date=bad").status_code, 200)
        for many in range(20):
            sup = Supplier.objects.create(name=f"Sup {many}")
            g = GRV.objects.create(supplier=sup, date="2026-10-16")
            GRVLine.objects.create(grv=g, ingredient=Ingredient.objects.get(), packs=1, pack_price=D("23"))
        self.assertContains(self.client.get("/reports/print/?month=2026-10"), "10 other suppliers")
