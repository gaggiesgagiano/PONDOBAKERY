import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase, override_settings


class ExamTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ov = override_settings(DATA_DIR=Path(self.tmp))
        self.ov.enable()
        d = Path(self.tmp) / "private" / "exams"
        d.mkdir(parents=True)
        (d / "SOP exam - Paper 1.pdf").write_bytes(b"%PDF-1.4 paper")
        (d / "SOP exam - Paper 1 MEMO (managers only).pdf").write_bytes(b"%PDF-1.4 memo")
        self.boss = User.objects.create_superuser("boss", "b@x.co", "Secret-pass-1")
        self.staff = User.objects.create_user("cash", "c@x.co", "Staff-pass-1")

    def tearDown(self):
        self.ov.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_staff_cannot_see(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/exams/").status_code, 404)
        self.assertEqual(self.client.get("/exams/file/SOP exam - Paper 1.pdf").status_code, 404)

    def test_owner_needs_password(self):
        self.client.force_login(self.boss)
        r = self.client.get("/exams/")
        self.assertContains(r, "Type your password")
        self.assertNotContains(r, "Paper 1")
        self.assertEqual(self.client.get("/exams/file/SOP exam - Paper 1.pdf").status_code, 302)
        self.client.post("/exams/", {"password": "wrong"})
        self.assertContains(self.client.get("/exams/"), "Type your password")
        self.client.post("/exams/", {"password": "Secret-pass-1"})
        r = self.client.get("/exams/")
        self.assertContains(r, "Paper 1 MEMO")
        r = self.client.get("/exams/file/SOP exam - Paper 1.pdf")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 paper")
        self.assertEqual(self.client.get("/exams/file/..%2Fsecret.key").status_code, 404)
        self.client.post("/exams/lock/")
        self.assertContains(self.client.get("/exams/"), "Type your password")

    def test_too_many_wrong(self):
        self.client.force_login(self.boss)
        for _ in range(5):
            self.client.post("/exams/", {"password": "nope"})
        self.client.post("/exams/", {"password": "Secret-pass-1"})
        self.assertContains(self.client.get("/exams/"), "Type your password")
