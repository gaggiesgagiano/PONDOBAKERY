"""Online mode (Pondo on a server): backups are downloaded, the brand font stays private, guessing passwords is blocked."""
import zipfile
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from core.models import LoginRecord


class OnlineTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_superuser("boss", "b@x.co", "pw-long-enough")

    @override_settings(ONLINE=True)
    @mock.patch("core.backup._copy_db", side_effect=lambda dest: (dest.write_bytes(b"db"), dest)[1])
    def test_backup_download_and_private_font(self, _copy):
        self.assertEqual(self.client.get("/static/fonts/retro-star.woff2").status_code, 404)  # strangers: no font
        self.client.force_login(self.boss)
        r = self.client.get("/backup/")
        self.assertContains(r, "Download backup")
        r = self.client.post("/backup/")
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(BytesIO(b"".join(r.streaming_content)))
        self.assertIn("pondo.sqlite3", z.namelist())
        self.assertNotEqual(self.client.get("/static/fonts/retro-star.woff2").status_code, 404)  # logged in: font

    def test_too_many_wrong_passwords(self):
        for _ in range(5):
            self.client.post("/login/", {"username": "boss", "password": "wrong"})
        self.assertEqual(LoginRecord.objects.filter(event="failed").count(), 5)
        r = self.client.post("/login/", {"username": "boss", "password": "pw-long-enough"})
        self.assertContains(r, "Too many wrong passwords")
        self.assertNotIn("_auth_user_id", self.client.session)
