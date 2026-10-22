from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Access

from .models import Advance, Employee, LeaveRecord, PayeBand, PayLine, PayrollSettings, PayRun
from .paycalc import band_list, paye, work_out


class PayMathsTests(TestCase):
    def setUp(self):
        self.s = PayrollSettings.get()
        self.bands = band_list(PayeBand.objects.all())

    def line(self, **kw):
        base = dict(pay_type="monthly", rate=D("500"))
        base.update(kw)
        return work_out(PayLine(**base), self.s, self.bands)

    def test_zimra_table_examples(self):
        self.assertEqual(paye(D("100"), self.bands), D("0"))
        self.assertEqual(paye(D("1800"), self.bands), D("455.00"))   # ZIMRA's own worked example
        self.assertEqual(paye(D("250"), self.bands), D("30.00"))
        self.assertEqual(paye(D("5000"), self.bands), D("1665.00"))

    def test_monthly_salary(self):
        ln = self.line()
        self.assertEqual((ln.gross, ln.nssa, ln.taxable, ln.paye, ln.aids_levy), (D("500"), D("22.50"), D("477.50"), D("84.38"), D("2.53")))
        self.assertEqual(ln.net, D("390.59"))
        self.assertEqual((ln.nssa_employer, ln.zimdef), (D("22.50"), D("5.00")))

    def test_nssa_ceiling_and_higher_band(self):
        ln = self.line(rate=D("1200"))
        self.assertEqual(ln.nssa, D("31.50"))  # 4.5% of the $700 ceiling
        self.assertEqual(ln.paye, D("265.55"))
        self.assertEqual(ln.net, D("894.98"))

    def test_day_rate_with_overtime_and_unpaid_days(self):
        ln = self.line(pay_type="daily", rate=D("20"), days=D("22"), overtime_hours=D("10"))
        self.assertEqual((ln.basic, ln.overtime_pay, ln.gross), (D("440.00"), D("37.50"), D("477.50")))
        self.assertEqual((ln.nssa, ln.paye, ln.aids_levy, ln.net), (D("21.49"), D("79.00"), D("2.37"), D("374.64")))
        m = self.line(rate=D("520"), unpaid_days=D("2"))  # 520/26 = 20 a day
        self.assertEqual(m.basic, D("480.00"))

    def test_no_nssa_no_paye_and_deductions(self):
        ln = work_out(PayLine(pay_type="hourly", rate=D("2"), hours=D("100"), advances=D("50")), self.s, self.bands,
                      pays_nssa=False, pays_paye=False)
        self.assertEqual((ln.gross, ln.nssa, ln.paye, ln.net), (D("200.00"), D("0"), D("0"), D("150.00")))


class PayrollFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.ann = Employee.objects.create(first_name="Ann", last_name="Moyo", rate=D("500"), transport_allowance=D("20"))
        self.ben = Employee.objects.create(first_name="Ben", last_name="Dube", pay_type="daily", rate=D("20"))
        Advance.objects.create(employee=self.ann, date="2026-10-05", amount=D("30"))
        Advance.objects.create(employee=self.ann, date="2026-10-08", amount=D("40"))

    def test_whole_pay_run(self):
        for url in ("/staff/", "/staff/new/", f"/staff/{self.ann.pk}/", "/staff/payroll/", "/staff/payroll/settings/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        r = self.client.post("/staff/payroll/new/", {"month": "2026-10", "pay_date": "2026-10-30"})
        run = PayRun.objects.get()
        self.assertRedirects(r, f"/staff/payroll/{run.pk}/edit/", fetch_redirect_response=False)
        a = run.lines.get(employee=self.ann)
        self.assertEqual((a.allowances, a.advances), (D("20"), D("70")))
        self.assertEqual(self.client.get(f"/staff/payroll/{run.pk}/edit/").status_code, 200)
        b = run.lines.get(employee=self.ben)
        data = {f"l{a.pk}-advances": "50", f"l{a.pk}-allowances": "20", f"l{a.pk}-overtime_hours": "",
                f"l{b.pk}-days": ""}
        r = self.client.post(f"/staff/payroll/{run.pk}/edit/", data)
        self.assertEqual(r.status_code, 200)  # Ben needs days
        self.assertContains(r, "Type the days Ben worked")
        data[f"l{b.pk}-days"] = "24"
        self.assertEqual(self.client.post(f"/staff/payroll/{run.pk}/edit/", data).status_code, 302)
        b.refresh_from_db()
        self.assertEqual(b.gross, D("480.00"))
        for url in (f"/staff/payroll/{run.pk}/", f"/staff/payroll/{run.pk}/payslips/", f"/staff/payroll/{run.pk}/summary/",
                    f"/staff/payroll/{run.pk}/payslips/{self.ann.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.post(f"/staff/payroll/{run.pk}/status/", {"to": "final"})
        run.refresh_from_db()
        self.assertEqual(run.status, "final")
        # $50 of $70 taken off: first advance fully, second split 20 / 20
        open_ = Advance.objects.filter(employee=self.ann, recovered_in__isnull=True)
        self.assertEqual(sum(x.amount for x in open_), D("20"))
        self.assertEqual(sum(x.amount for x in Advance.objects.filter(recovered_in__run=run)), D("50"))
        # final runs can't be edited; owner can re-open
        self.assertEqual(self.client.get(f"/staff/payroll/{run.pk}/edit/").status_code, 302)
        self.client.post(f"/staff/payroll/{run.pk}/status/", {"to": "draft"})
        self.assertEqual(Advance.objects.filter(employee=self.ann, recovered_in__isnull=True).count(), 3)
        # report sees wages only for final runs
        from sales.report import month_report
        import datetime
        self.assertEqual(month_report(datetime.date(2026, 10, 1))["wages_cost"], D("0"))

    def test_leave_and_advance_screens(self):
        r = self.client.post(f"/staff/{self.ann.pk}/leave/", {"kind": "annual", "start": "2026-10-05", "end": "2026-10-10", "days": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(LeaveRecord.objects.get().days, D("6"))  # Mon–Sat
        self.client.post(f"/staff/{self.ann.pk}/advance/", {"date": "2026-10-09", "amount": "15", "reason": "bus"})
        self.assertEqual(self.ann.open_advances().count(), 3)

    def test_settings_change_reworks_drafts(self):
        self.client.post("/staff/payroll/new/", {"month": "2026-10", "pay_date": "2026-10-30"})
        run = PayRun.objects.get()
        before = run.lines.get(employee=self.ann).nssa
        page = self.client.get("/staff/payroll/settings/")
        data = {"nssa_pct": "4.5", "nssa_er_pct": "4.5", "aids_pct": "3", "zimdef_pct": "1", "nssa_ceiling": "300",
                "normal_days": "26", "normal_hours": "208", "day_hours": "8", "overtime_rate": "1.5", "holiday_rate": "2",
                "tax_table_note": "test"}
        bands = list(PayeBand.objects.all())
        data.update({"b-TOTAL_FORMS": str(len(bands) + 1), "b-INITIAL_FORMS": str(len(bands)), "b-MIN_NUM_FORMS": "0", "b-MAX_NUM_FORMS": "1000"})
        for i, b in enumerate(bands):
            data.update({f"b-{i}-id": str(b.pk), f"b-{i}-up_to": "" if b.up_to is None else str(b.up_to),
                         f"b-{i}-rate_pct": str((b.rate * 100).normalize()), f"b-{i}-deduct": str(b.deduct)})
        r = self.client.post("/staff/payroll/settings/", data)
        self.assertEqual(r.status_code, 302, [m for m in __import__("re").findall(r"class=\"(?:err|msg error)\"[^>]*>([^<]*)", r.content.decode())])
        self.assertEqual(run.lines.get(employee=self.ann).nssa, D("13.50"))
        self.assertNotEqual(before, D("13.50"))

    def test_rights(self):
        u = User.objects.create_user("baker", password="TestPass123!")
        Access.from_preset(u, "baker")
        self.client.logout()
        self.client.login(username="baker", password="TestPass123!")
        self.assertRedirects(self.client.get("/staff/"), "/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/sales/"), "/", fetch_redirect_response=False)
        self.assertNotContains(self.client.get("/"), "Staff &amp; Payroll")
