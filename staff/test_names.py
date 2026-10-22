import datetime
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Employee, PayRun


class NameTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_superuser("boss", "", "pw")
        self.client.force_login(self.u)
        self.s = Employee.objects.create(code="26003", known_as="Sidney", first_name="Sydney", middle_name="Talent",
                                         last_name="Ndlovu", job_title="Confectioner", rate=D("550"))
        self.o = Employee.objects.create(code="26016", first_name="", job_title="Counter hand", rate=D("380"))

    def test_names(self):
        self.assertEqual(self.s.name, "Sidney Ndlovu")
        self.assertEqual(self.s.full_name, "Sydney Talent Ndlovu")
        self.assertEqual(self.s.initials, "SN")
        self.assertTrue(self.o.is_open)
        self.assertEqual(self.o.name, "Open – Counter hand")

    def test_pages(self):
        r = self.client.get("/staff/")
        self.assertContains(r, "Sidney Ndlovu")
        self.assertContains(r, "Open – Counter hand")
        self.assertLess(r.content.find(b"Sidney Ndlovu"), r.content.find(b"Open \xe2\x80\x93 Counter hand"))
        self.assertContains(self.client.get("/staff/?q=talent"), "Sidney Ndlovu")
        r = self.client.get(f"/staff/{self.s.pk}/")
        self.assertContains(r, "Sydney Talent Ndlovu")
        r = self.client.get(f"/staff/{self.s.pk}/edit/")
        self.assertContains(r, "Known as")
        self.assertContains(r, "Second name")

    def test_open_place_not_paid(self):
        r = self.client.post("/staff/payroll/new/", {"month": "2026-10", "pay_date": "2026-10-30"})
        run = PayRun.objects.get()
        self.assertEqual([ln.employee_id for ln in run.lines.all()], [self.s.pk])
