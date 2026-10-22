import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from .calc import count_summary, depreciation_for_month, year_schedule
from .models import EquipmentCategory, Item, Location

OCT = datetime.date(2026, 10, 1)


class EquipmentTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.ovens = EquipmentCategory.objects.get(name="Ovens & Proofers")  # 10 years (from the Excel lists)
        self.trays = EquipmentCategory.objects.get(name="Trays, Tins & Smallwares")  # 3 years
        self.bakery = Location.objects.get(name="Night Bakery")
        # like the Excel EQ-001: $17,846.45, 10 years -> $148.72 a month from April 2026
        self.oven = Item.objects.create(asset_no="EQ-001", description="Rack oven", category=self.ovens, location=self.bakery,
                                        purchase_date="2026-04-24", unit_cost=D("17846.45"), qty=1)
        self.tins = Item.objects.create(asset_no="EQ-002", description="Bread tins", category=self.trays, location=self.bakery,
                                        purchase_date="2026-01-10", unit_cost=D("10"), qty=36, scrap_value=D("0"))
        self.oven.refresh_from_db()
        self.tins.refresh_from_db()

    def test_straight_line_like_excel(self):
        self.assertEqual(round(self.oven.per_month, 2), D("148.72"))
        self.assertEqual(self.oven.months_until(OCT), 7)  # Apr..Oct, the buying month counts
        self.assertEqual(round(self.oven.dep_to(OCT), 2), D("1041.04"))
        self.assertEqual(round(self.oven.book_value(OCT), 2), D("16805.41"))
        self.assertEqual(self.oven.dep_in(datetime.date(2026, 3, 1)), 0)  # not bought yet
        self.assertEqual(self.tins.per_month, D("10"))  # 360 over 36 months
        self.assertEqual(depreciation_for_month(OCT), self.oven.per_month + 10)
        # written off in October: depreciation that month, nothing after, book value 0
        self.tins.disposed_on = datetime.date(2026, 10, 15)
        self.tins.save()
        self.assertEqual(self.tins.dep_in(OCT), D("10"))
        self.assertEqual(self.tins.dep_in(datetime.date(2026, 11, 1)), 0)
        self.assertEqual(self.tins.book_value(OCT), 0)
        s = year_schedule(datetime.date(2026, 1, 1))
        self.assertEqual(s["totals"][0], D("10"))          # January: only the tins
        self.assertEqual(s["totals"][3], self.oven.per_month + 10)

    def test_count_and_pages(self):
        r = self.client.post("/equipment/count/?month=2026-10", {"counted_by": "Sydney", "date": "2026-10-31", "notes": "",
                                                                 f"i{self.oven.pk}": "1", f"i{self.tins.pk}": "30"})
        self.assertEqual(r.status_code, 302)
        s = count_summary(OCT)
        self.assertEqual((s["counted"], s["missing_pieces"], s["missing_value"]), (2, 6, D("60")))
        for url in ("/equipment/", "/equipment/new/", f"/equipment/{self.oven.pk}/", "/equipment/count/?month=2026-10",
                    "/equipment/depreciation/?year=2026", "/equipment/lists/", "/reports/?month=2026-10"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get("/equipment/count/?month=2026-10"), "6 missing")
        self.assertContains(self.client.get("/reports/?month=2026-10"), "Pieces missing")
        page = self.client.get("/equipment/new/")
        self.assertContains(page, 'value="EQ-003"')  # next free number
