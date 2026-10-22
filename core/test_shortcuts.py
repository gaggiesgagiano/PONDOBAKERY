import datetime

from django.contrib.auth.models import User
from django.test import TestCase

from .access import Rights
from .jobs import JOBS, available, standard
from .models import Access


class ShortCutTests(TestCase):
    """Every Short Cut builds for every role without errors; Till and Fiscal are there by default."""

    def test_every_tile_builds(self):
        boss = User.objects.create_superuser("boss", password="Boss-pass-1")
        cashier = User.objects.create_user("rudo", password="Rudo-pass-1")
        Access.from_preset(cashier, "cashier")
        baker = User.objects.create_user("baker", password="Baker-pass-1")
        Access.from_preset(baker, "baker")
        d = datetime.date.today()
        for user in (boss, cashier, baker):
            can = Rights(user)
            for key, name, *_ in available(can, user):
                if key in JOBS:
                    fn = JOBS[key][4]
                    tile = fn(can, d, True) if key == "backup" else fn(can, d)
                    if tile:
                        self.assertTrue(tile["url"].startswith("/"), (key, tile))
        self.assertGreaterEqual(len(available(Rights(boss), boss)), 45)
        self.assertIn("till", standard(Rights(cashier), cashier))
        self.assertIn("fiscal", standard(Rights(cashier), cashier))
        self.assertNotIn("zwg_rate", standard(Rights(cashier), cashier))     # Manager only
        self.client.login(username="boss", password="Boss-pass-1")
        page = self.client.get("/")
        self.assertContains(page, "Till")
        self.assertContains(page, "ZWG rate")
        self.assertContains(self.client.get("/jobs/"), "New supplier order")      # the list to choose from
