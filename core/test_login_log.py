"""Login register: log-ins, log-outs and wrong passwords are written down with where they came from."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from core.login_log import device_name
from core.models import LoginRecord


class LoginRegisterTests(TestCase):
    def test_in_out_failed(self):
        U = get_user_model()
        boss = U.objects.create_superuser("boss", "b@x.co", "pw-long-enough")
        win = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
        self.client.post("/login/", {"username": "boss", "password": "wrong"}, HTTP_USER_AGENT=win)
        self.client.post("/login/", {"username": "boss", "password": "pw-long-enough"}, HTTP_USER_AGENT=win, REMOTE_ADDR="192.168.0.20")
        self.client.post("/logout/")
        ev = list(LoginRecord.objects.order_by("id").values_list("event", "username"))
        self.assertEqual(ev, [("failed", "boss"), ("in", "boss"), ("out", "boss")])
        r = LoginRecord.objects.get(event="in")
        self.assertEqual((r.device, r.where), ("Chrome on Windows", "Shop network · 192.168.0.20"))
        self.client.force_login(boss)
        page = self.client.get("/changes/?tab=logins")
        self.assertContains(page, "Wrong password")
        self.assertContains(page, "Chrome on Windows")

    def test_device_names(self):
        self.assertEqual(device_name("Mozilla/5.0 (Linux; Android 14; SM-A15) AppleWebKit Chrome/129 Mobile Safari/537.36"), "Chrome on Android phone")
        self.assertEqual(device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit Version/17.5 Mobile Safari/604.1"), "Safari on iPhone")
