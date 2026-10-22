from html import escape
from django.contrib.auth.models import User
from django.test import TestCase

from core.blank_forms import FORMS
from core.models import Access


class BlankFormTests(TestCase):
    def test_every_form_prints(self):
        self.client.force_login(User.objects.create_superuser("boss", "", "pw"))
        r = self.client.get("/forms/")
        self.assertContains(r, "Leave application")
        for key, f in FORMS.items():
            r = self.client.get(f"/forms/{key}/")
            self.assertEqual(r.status_code, 200, key)
            self.assertContains(r, escape(f[0]))
            self.assertContains(r, "@page")
        self.assertEqual(self.client.get("/forms/nothing/").status_code, 404)

    def test_cashier_sees_only_open_forms(self):
        u = User.objects.create_user("cash", "", "pw")
        Access.from_preset(u, "cashier")
        self.client.force_login(u)
        r = self.client.get("/forms/")
        self.assertContains(r, "Customer order form")
        self.assertContains(r, "Leave application")
        self.assertNotContains(r, "Fixed term employment contract")
        self.assertEqual(self.client.get("/forms/contract/").status_code, 404)
