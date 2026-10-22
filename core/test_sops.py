"""SOP file: list, edit with versions, approval, sign-offs, printing and rights."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Access, Sop, SopRead
from core.richtext import clean_doc
from staff.models import Employee


class SopTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.boss = U.objects.create_superuser("boss", "b@x.co", "pw-long-enough")
        self.client.force_login(self.boss)
        self.a = Employee.objects.create(first_name="Anna", last_name="Baker", department="production")
        self.b = Employee.objects.create(first_name="Ben", last_name="Till", department="shop")

    def test_first_draft_is_loaded(self):
        self.assertGreaterEqual(Sop.objects.count(), 40)
        self.assertFalse(Sop.objects.exclude(status=Sop.DRAFT).exists())
        r = self.client.get("/sops/")
        self.assertContains(r, "SOP file")
        self.assertContains(r, "Opening the shop")

    def test_edit_approve_version_and_signoff(self):
        s = Sop.objects.get(section=1, seq=1)
        self.assertEqual([e.pk for e in s.readers()], [self.a.pk, self.b.pk])
        r = self.client.post(f"/sops/{s.pk}/approve/", {"approved_by": "Owner / Director", "approved_on": "2026-10-18"})
        s.refresh_from_db()
        self.assertEqual((s.status, s.approved_on, s.review_due), ("approved", datetime.date(2026, 10, 18), datetime.date(2027, 10, 18)))
        self.client.post(f"/sops/{s.pk}/signed/", {"emp": [self.a.pk], "signed_on": "2026-10-19"})
        self.assertEqual(SopRead.objects.get(sop=s, employee=self.a).version, 1)
        # change the approved SOP: v1 kept, v2 is a draft, Anna must read again
        r = self.client.post(f"/sops/{s.pk}/edit/", {"section": 1, "seq": 1, "title": s.title, "purpose": s.purpose,
                                                    "responsible": s.responsible, "applies_list": ["all"],
                                                    "body": s.body + "<p>New <script>bad()</script>step</p>", "note": "added a step"})
        self.assertEqual(r.status_code, 302)
        s.refresh_from_db()
        self.assertEqual((s.version, s.status), (2, "draft"))
        self.assertNotIn("script", s.body)
        self.assertEqual(s.versions.get().note, "added a step")
        r = self.client.get("/sops/staff/")
        self.assertContains(r, "read again")
        for url in (f"/sops/{s.pk}/", "/sops/print/", f"/sops/print/?sop={s.pk}", f"/sops/{s.pk}/sheet/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertContains(self.client.get(f"/sops/{s.pk}/sheet/"), "Anna Baker")

    def test_duplicate_number_refused(self):
        r = self.client.post("/sops/new/", {"section": 1, "seq": 1, "title": "X", "purpose": "Y", "applies_list": ["all"],
                                            "body": "<p>Z</p>"})
        self.assertContains(r, "already")

    def test_rights(self):
        U = get_user_model()
        u = U.objects.create_user("cash", password="pw-long-enough")
        Access.from_preset(u, "cashier")
        self.client.force_login(u)
        s = Sop.objects.first()
        self.assertEqual(self.client.get(f"/sops/{s.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/sops/{s.pk}/edit/").status_code, 302)
        self.client.post(f"/sops/{s.pk}/approve/", {"approved_on": "2026-10-18"})
        s.refresh_from_db()
        self.assertEqual(s.status, "draft")

    def test_clean_doc(self):
        self.assertEqual(clean_doc("<ol><li>a<li>b</ol><h1>T</h1><img src=x onerror=y>"), "<ol><li>a</li><li>b</li></ol><h3>T</h3>")
