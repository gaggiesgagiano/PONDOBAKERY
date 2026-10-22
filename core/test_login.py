from django.contrib.auth.models import User
from django.test import TestCase


class LoginTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")

    def test_keep_me_logged_in(self):
        self.assertContains(self.client.get("/login/"), 'name="remember"')
        r = self.client.post("/login/", {"username": "owner", "password": "TestPass123!", "remember": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.session.get_expiry_age(), 30 * 24 * 3600)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertTrue(r.cookies["sessionid"]["expires"])  # stays after the browser closes

    def test_normal_login_ends_with_the_browser(self):
        r = self.client.post("/login/", {"username": "owner", "password": "TestPass123!"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertFalse(r.cookies["sessionid"]["expires"])
