import base64
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core import backup

from .models import Recipe

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
TMP = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP)
class PhotoTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.r = Recipe.objects.create(number=5, name="Chelsea Bun", sell_price=1)

    def test_add_show_back_up_and_remove(self):
        url = f"/recipes/{self.r.pk}/photo/"
        r = self.client.post(url, {"photo": SimpleUploadedFile("bun.txt", b"hello", content_type="text/plain")})
        self.r.refresh_from_db()
        self.assertFalse(self.r.photo)  # not a picture
        self.client.post(url, {"photo": SimpleUploadedFile("IMG_1234.png", PNG, content_type="image/png")})
        self.r.refresh_from_db()
        self.assertEqual(self.r.photo.name, "recipes/5-chelsea-bun.png")
        first = Path(self.r.photo.path)
        self.assertTrue(first.exists())
        for page in (f"/recipes/{self.r.pk}/", "/recipes/", "/recipes/?show=products", f"/recipes/{self.r.pk}/print/card/"):
            self.assertContains(self.client.get(page), self.r.photo.url, msg_prefix=page)
        drive = tempfile.mkdtemp()
        backup.copy_photos(Path(drive) / "Pondo Backups")
        self.assertTrue((Path(drive) / "Pondo Backups" / "photos" / "recipes" / "5-chelsea-bun.png").exists())
        self.client.post(url, {"photo": SimpleUploadedFile("new.jpg", PNG, content_type="image/jpeg")})
        self.r.refresh_from_db()
        self.assertTrue(self.r.photo.name.endswith(".jpg"))
        self.assertFalse(first.exists())  # the old photo is cleaned up
        self.client.post(url, {"remove": "1"})
        self.r.refresh_from_db()
        self.assertFalse(self.r.photo)
        self.assertContains(self.client.get(f"/recipes/{self.r.pk}/"), "No photo yet")
