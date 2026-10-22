import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from costing.models import Category, Ingredient, Recipe, RecipeLine
from production.models import WasteLine, WasteLog
from sales.models import DailySales
from staff.models import Employee

from .daily import dashboard_data
from .models import CompanySettings, Overhead
from .targets import Targets


class DashboardTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        cs = CompanySettings.get()
        cs.profit_target, cs.trading_days, cs.waste_target = D("6000"), 6, D("0.05")
        cs.save()
        Overhead.objects.create(name="Rent", monthly_cost=D("2000"))
        Employee.objects.create(first_name="Ann", rate=D("1000"), transport_allowance=D("50"))
        Employee.objects.create(first_name="Ben", pay_type="daily", rate=D("10"))
        Employee.objects.create(first_name="Old", rate=D("999"), active=False)
        self.bread = Category.objects.create(name="Bread")
        self.cakes = Category.objects.create(name="Cakes")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("1"))
        # 10 kg flour -> 20 loaves at $0.50 cost; sells $1.00 excl. VAT (zero-rated) -> GP 50%
        self.loaf = Recipe.objects.create(number=1, name="Loaf", category=self.bread, scaling_weight=D("0.5"),
                                          sell_price=D("1.00"), vat_rate=D("0"))
        RecipeLine.objects.create(recipe=self.loaf, ingredient=flour, qty=10)
        # cake: cost 0.25 each (5 kg / 20), sells 1.00 -> GP 75%
        self.cake = Recipe.objects.create(number=2, name="Cake", category=self.cakes, yield_override=20,
                                          sell_price=D("1.00"), vat_rate=D("0"))
        RecipeLine.objects.create(recipe=self.cake, ingredient=flour, qty=5)

    def test_targets_like_the_excel_sheet(self):
        t = Targets()
        days = D(6) * D(52) / D(12)
        self.assertEqual(t.wages, D("1050") + D("10") * days)  # Old has left
        self.assertEqual(t.staff_count, 2)
        self.assertEqual(t.costs_month, t.wages + D("2000"))
        self.assertEqual(t.gp, D("0.625"))  # average of 50% and 75%
        self.assertAlmostEqual(float(t.costs_day), float(t.costs_month / (D(52) / D(12)) / 6), places=6)
        self.assertAlmostEqual(float(t.be_month), float(t.costs_month / D("0.625")), places=6)
        self.assertAlmostEqual(float(t.bep_month), float((t.costs_month + 6000) / D("0.625")), places=6)
        cs = CompanySettings.get()
        cs.gp_override = D("0.5")
        cs.save()
        self.assertEqual(Targets().gp, D("0.5"))

    def test_daily_sales_and_dashboard(self):
        mon, tue = datetime.date(2026, 10, 5), datetime.date(2026, 10, 6)
        page = self.client.get(f"/sales/daily/{mon}/")
        self.assertContains(page, "Bread")
        r = self.client.post(f"/sales/daily/{mon}/", {f"c{self.bread.pk}": "600", f"c{self.cakes.pk}": "400", "gp": "", "go": "next"})
        self.assertRedirects(r, f"/sales/daily/{tue}/", fetch_redirect_response=False)
        day = DailySales.objects.get(date=mon)
        self.assertEqual((day.total, day.gp_amount), (D("1000.00"), D("600.00")))  # 600×50% + 400×75%
        self.client.post(f"/sales/daily/{tue}/", {f"c{self.bread.pk}": "500", "gp": "60", "go": "list"})
        self.assertEqual(DailySales.objects.get(date=tue).gp_amount, D("300.00"))  # typed GP wins
        bad = self.client.post(f"/sales/daily/{tue}/", {f"c{self.bread.pk}": "abc", "gp": "", "go": "list"})
        self.assertContains(bad, "is not an amount")
        # waste on Monday, looked at from Tuesday
        log = WasteLog.objects.create(date=mon, shift="day")
        WasteLine.objects.create(log=log, recipe=self.loaf, qty=D("100"), reason="Expired", unit_cost=D("0.5"))

        data = dashboard_data(tue)
        t, s = data["t"], data["s"]
        self.assertEqual(s["today"]["sales"], D("500"))
        self.assertEqual((s["week"]["sales"], s["week"]["days"]), (D("1500"), 2))
        self.assertEqual(s["month"]["gp_amount"], D("900"))
        self.assertAlmostEqual(float(s["month"]["be"]), float(t.be_day * 2), places=6)
        self.assertAlmostEqual(float(s["month"]["net"]), float(D("900") - t.costs_day * 2), places=6)
        cats = {c.name: v for c, v in data["cats"]["rows"]}
        self.assertEqual((cats["Bread"]["today"], cats["Bread"]["month"], cats["Cakes"]["week"]), (D("500"), D("1100"), D("400")))
        w = data["waste"]
        self.assertTrue(w["logged"])
        self.assertEqual((w["cols"]["today"]["cost"], w["cols"]["today"]["pct"]), (D("50.00"), D("0.05")))
        self.assertEqual(w["status"][0], "ok")  # exactly on the 5% limit
        self.assertEqual(data["rest"]["days_left"], round(25 * 6 / 7))

        for url in ("/", f"/?date={tue}", "/sales/", "/sales/daily/?month=2026-10", "/settings/costs/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(f"/?date={tue}"), "$1,500")
        # clearing a day removes it
        self.client.post(f"/sales/daily/{tue}/", {"gp": "", "go": "list"})
        self.assertFalse(DailySales.objects.filter(date=tue).exists())

    def test_costs_and_targets_page(self):
        r = self.client.post("/settings/costs/", {
            "profit_target": "20000", "trading_days": "7", "waste_percent": "4", "gp_percent": "",
            "o-TOTAL_FORMS": "2", "o-INITIAL_FORMS": "1", "o-MIN_NUM_FORMS": "0", "o-MAX_NUM_FORMS": "1000",
            "o-0-id": str(Overhead.objects.get().pk), "o-0-name": "Rent", "o-0-monthly_cost": "2500",
            "o-1-name": "Gas", "o-1-monthly_cost": "300"})
        self.assertEqual(r.status_code, 302)
        cs = CompanySettings.get()
        self.assertEqual((cs.profit_target, cs.trading_days, cs.waste_target), (D("20000"), 7, D("0.04")))
        self.assertEqual(Targets().overheads, D("2800"))
        self.assertEqual(Employee.objects.count(), 3)  # the Excel staff list is only added to the real database
