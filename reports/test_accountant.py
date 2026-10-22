import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Access


class AccountantReportTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_superuser("boss", "", "pw")
        self.client.force_login(self.u)

    def test_empty_month_prints_and_downloads(self):
        r = self.client.get("/reports/accountant/?month=2026-10")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Accountant month report")
        self.assertContains(r, "1 October 2026 – 31 October 2026")
        self.assertContains(r, "No daily sales typed")
        r = self.client.get("/reports/accountant/excel/?month=2026-10")
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])

    def test_with_expense_and_tile(self):
        from sales.models import Expense, ExpenseCategory
        cat = ExpenseCategory.objects.create(name="Test rent")
        Expense.objects.create(date=datetime.date(2026, 9, 3), category=cat, amount=D("115.50"), vat=D("15.50"),
                               paid_from=Expense.OWNER)
        r = self.client.get("/reports/accountant/?month=2026-09")
        self.assertContains(r, "$100.00")
        self.assertContains(r, "paid by the owner personally")
        from core.jobs import j_accountant
        from core.access import rights
        can = rights(type("Req", (), {"user": self.u, "session": {}})())
        t = j_accountant(can, datetime.date(2026, 10, 5))
        self.assertIn("September", t["sub"])
        self.assertIn("month=2026-09", t["url"])
        t = j_accountant(can, datetime.date(2026, 10, 20))
        self.assertIn("October so far", t["sub"])

    def test_cashier_cannot_open(self):
        c = User.objects.create_user("cash", "", "pw")
        Access.from_preset(c, "cashier")
        self.client.force_login(c)
        self.assertEqual(self.client.get("/reports/accountant/").status_code, 302)
