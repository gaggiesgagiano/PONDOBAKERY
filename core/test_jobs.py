"""Today's jobs: everybody chooses their own jobs and order, and adds their own jobs to tick off."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.models import Access, MyJob, MyJobDone, UserLook

from .access import Rights
from .jobs import chosen


class JobTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(self.owner)

    def jobs_html(self):
        s = self.client.get("/").content.decode()
        return s[s.index('aria-label="Short Cuts"'):s.index("</section>", s.index('aria-label="Short Cuts"'))]

    def test_standard_choose_and_order(self):
        html = self.jobs_html()
        self.assertIn("Type the day&#x27;s sales", html)
        self.assertIn("Receiving", html)
        self.assertNotIn("Low stock", html)  # not on by default
        self.assertContains(self.client.get("/jobs/"), "Low stock")
        r = self.client.post("/jobs/", {"order": "low_stock,cashup,sales,receiving", "on": ["low_stock", "cashup", "sales"]})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        self.assertEqual(chosen(Rights(self.owner), self.owner), ["low_stock", "cashup", "sales"])
        html = self.jobs_html()
        self.assertLess(html.index("Low stock"), html.index("Cash-up"))
        self.assertNotIn("Receiving", html)
        self.client.post("/jobs/", {"order": "sales"})  # nothing ticked
        self.assertIn("No short cuts chosen", self.jobs_html())
        self.client.post("/jobs/reset/")
        self.assertEqual(UserLook.objects.get(user=self.owner).jobs, "")
        self.assertIn("Receiving", self.jobs_html())

    def test_drag_and_drop_order(self):
        html = self.jobs_html()
        self.assertIn('data-key="sales"', html)
        self.assertIn("Drag the tiles", html)
        self.client.post("/jobs/", {"order": "sales,cashup,plan,receiving,low_stock", "on": ["sales", "cashup", "plan", "receiving"]})
        r = self.client.post("/jobs/order/", {"order": "receiving,sales,plan,cashup,bogus"})
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(chosen(Rights(self.owner), self.owner), ["receiving", "sales", "plan", "cashup"])
        self.assertIn("!low_stock", UserLook.objects.get(user=self.owner).jobs)  # a hidden job stays hidden
        html = self.jobs_html()
        self.assertLess(html.index("Receiving"), html.index("Cash-up"))
        self.assertEqual(self.client.post("/jobs/order/", {"order": ""}).status_code, 400)

    def test_my_own_jobs_and_ticks(self):
        r = self.client.post("/jobs/my/new/", {"title": "Clean the fridges", "note": "before 7", "link": "",
                                               "colour": "teal", "days_list": [str(d) for d in range(7)]})
        self.assertEqual(r.status_code, 302)
        mj = MyJob.objects.get()
        self.assertIn("Clean the fridges", self.jobs_html())
        self.client.post(f"/jobs/my/{mj.pk}/tick/", {"date": timezone.localdate().isoformat(), "next": "/"})
        self.assertTrue(MyJobDone.objects.filter(job=mj).exists())
        self.assertIn("✓ Done", self.jobs_html())
        self.client.post(f"/jobs/my/{mj.pk}/tick/", {"date": timezone.localdate().isoformat()})  # undo
        self.assertFalse(MyJobDone.objects.exists())
        # not on today's weekday: not shown
        other = str((timezone.localdate().weekday() + 1) % 7)
        self.client.post(f"/jobs/my/{mj.pk}/", {"title": "Clean the fridges", "link": "stock", "colour": "warm", "days_list": [other]})
        self.assertNotIn("Clean the fridges", self.jobs_html())
        self.client.post("/jobs/my/new/", {"title": "", "colour": "teal", "days_list": []})
        self.assertEqual(MyJob.objects.count(), 1)  # title and days are needed

    def test_shared_job_for_everybody_and_rights(self):
        self.client.post("/jobs/my/new/", {"title": "Lock the back door", "link": "", "colour": "burgundy",
                                           "days_list": [str(d) for d in range(7)], "shared": "on"})
        till = User.objects.create_user("till", password="x")
        Access.from_preset(till, "cashier")
        self.client.force_login(till)
        html = self.jobs_html()
        self.assertIn("Lock the back door", html)
        self.assertNotIn("Production plan", html)  # a cashier has no production rights
        r = self.client.get("/jobs/")
        self.assertNotContains(r, "Staff papers")
        self.assertNotContains(r, 'name="shared"')
        mj = MyJob.objects.get()
        self.client.post(f"/jobs/my/{mj.pk}/tick/", {"date": timezone.localdate().isoformat()})
        self.client.force_login(self.owner)
        self.assertIn("✓ Done", self.jobs_html())  # done for everybody
        self.client.force_login(till)
        self.client.post(f"/jobs/my/{mj.pk}/delete/")
        self.assertTrue(MyJob.objects.filter(pk=mj.pk).exists())  # only its maker or the owner
