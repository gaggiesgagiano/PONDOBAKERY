from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from core import barcode128
from core.cards import approver
from core.models import Access, StaffCard
from staff.models import Employee


class StaffCardTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser("boss", "", "pw-boss-123")
        self.sup = User.objects.create_user("sup", password="pw-sup-123", first_name="Rudo")
        a, _ = Access.objects.get_or_create(user=self.sup)
        a.role = "supervisor"
        a.save()
        self.tendai = Employee.objects.create(first_name="Tendai", last_name="Moyo", code="26001", job_title="Cashier", department="shop")
        self.rudo = Employee.objects.create(first_name="Rudo", last_name="Ncube", code="26002", job_title="Day Supervisor")
        Employee.objects.create(job_title="Baker")  # open position – no card

    def boss_post(self, url, data=None):
        self.client.force_login(self.boss)
        r = self.client.post(url, data or {})
        self.client.logout()
        return r

    def test_barcode_svg(self):
        self.assertIn("<rect", barcode128.svg("PBABC2345XY"))

    def test_owner_only(self):
        self.client.force_login(self.sup)
        self.assertNotEqual(self.client.get("/settings/cards/").status_code, 200)
        self.client.force_login(self.boss)
        r = self.client.get("/settings/cards/")
        self.assertContains(r, "Tendai Moyo")
        self.assertContains(r, "26001")

    def test_make_all_and_print(self):
        self.boss_post("/settings/cards/all/")
        self.assertEqual(StaffCard.objects.filter(employee__isnull=False).count(), 2)
        self.client.force_login(self.boss)
        r = self.client.get("/settings/cards/print/")
        self.assertContains(r, "26001")
        self.assertContains(r, "Day Supervisor")
        self.assertEqual(r.content.decode().count("<svg"), 2)
        self.boss_post("/settings/cards/all/")          # again: nothing new
        self.assertEqual(StaffCard.objects.count(), 2)

    def test_card_without_login_then_linked(self):
        self.boss_post(f"/settings/cards/staff/{self.rudo.pk}/new/")
        code = StaffCard.objects.get(employee=self.rudo).code
        self.assertIn("card=nologin", self.client.post("/login/card/", {"card": code})["Location"])
        self.assertIsNone(approver(RequestFactory().post("/", {"card": code})))
        self.boss_post(f"/settings/cards/{self.rudo.pk}/login/", {"user": self.sup.pk})
        self.client.post("/login/card/", {"card": code})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.sup.pk)
        self.assertEqual(approver(RequestFactory().post("/", {"card": code})), self.sup)

    def test_login_card_merges_into_staff_card(self):
        self.boss_post(f"/settings/cards/login/{self.sup.pk}/new/")
        old = StaffCard.objects.get(user=self.sup).code
        self.boss_post(f"/settings/cards/{self.rudo.pk}/login/", {"user": self.sup.pk})
        self.assertEqual(StaffCard.objects.filter(user=self.sup).count(), 1)
        self.assertEqual(StaffCard.objects.get(user=self.sup).employee, self.rudo)
        self.assertIsNone(approver(RequestFactory().post("/", {"card": old})))

    def test_new_card_kills_old_and_leaver_blocked(self):
        self.boss_post(f"/settings/cards/staff/{self.rudo.pk}/new/")
        self.boss_post(f"/settings/cards/{self.rudo.pk}/login/", {"user": self.sup.pk})
        old = StaffCard.objects.get(employee=self.rudo).code
        self.boss_post(f"/settings/cards/staff/{self.rudo.pk}/new/")
        new = StaffCard.objects.get(employee=self.rudo).code
        self.assertNotEqual(old, new)
        rf = RequestFactory()
        self.assertIsNone(approver(rf.post("/", {"card": old})))
        self.assertEqual(approver(rf.post("/", {"card": new.lower()})), self.sup)
        self.rudo.active = False
        self.rudo.save()
        self.assertIsNone(approver(rf.post("/", {"card": new})))

    def test_stop(self):
        self.boss_post(f"/settings/cards/login/{self.sup.pk}/new/")
        c = StaffCard.objects.get(user=self.sup)
        self.boss_post(f"/settings/cards/{c.pk}/stop/")
        self.assertIn("card=bad", self.client.post("/login/card/", {"card": c.code})["Location"])

    def test_password_approval_still_works(self):
        self.assertEqual(approver(RequestFactory().post("/", {"by": "sup", "pw": "pw-sup-123"})), self.sup)

    def test_login_page_has_scan_box(self):
        self.assertContains(self.client.get("/login/"), 'name="card"')
