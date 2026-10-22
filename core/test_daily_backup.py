"""Daily backup: pop-up after a cash-up, Pondo locked the next day without a backup, unlocked by the backup or the Manager."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.models import Access, CompanySettings
from sales.models import CashUp

D1 = datetime.date(2099, 1, 5)
D2 = datetime.date(2099, 1, 6)


class DailyBackupTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.boss = U.objects.create_superuser("boss", "b@x.co", "pw-long-enough")
        self.cashier = U.objects.create_user("cash", password="pw-long-enough")
        Access.from_preset(self.cashier, "cashier")

    def test_lock_and_unlock(self):
        with mock.patch("django.utils.timezone.localdate", return_value=D1):
            cu = CashUp.objects.create(date=D1, till="Till 1")
            self.client.force_login(self.cashier)
            r = self.client.get(f"/sales/cashup/{cu.pk}/?saved=1")
            self.assertContains(r, "Last cash-up of the day?")
            self.assertContains(r, "Tell the Supervisor or Manager")
            self.assertEqual(self.client.get("/").status_code, 200)        # same day: not locked
        with mock.patch("django.utils.timezone.localdate", return_value=D2):
            r = self.client.get("/")
            self.assertRedirects(r, "/backup/needed/", fetch_redirect_response=False)
            self.assertContains(self.client.get("/backup/needed/"), "Call the Supervisor or Manager")
            # the Manager opens Pondo for today with a reason
            self.client.force_login(self.boss)
            self.client.post("/backup/waive/", {"reason": "flash drive broken"})
            self.assertEqual(self.client.get("/").status_code, 200)
        cs = CompanySettings.get()
        cs.backup_waived_on = None
        cs.last_flash_backup = timezone.now()                                # a backup made after the cash-up
        cs.save()
        with mock.patch("django.utils.timezone.localdate", return_value=D2):
            self.client.force_login(self.cashier)
            self.assertEqual(self.client.get("/").status_code, 200)

    def test_no_cashups_no_lock(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get("/").status_code, 200)
