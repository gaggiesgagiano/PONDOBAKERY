"""The roles: Manager (top login), Assistant Manager, Supervisor, Admin, Cashier, Baker."""
from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Access


class RoleTests(TestCase):
    def login_as(self, role):
        u = User.objects.create_user(role, password="TestPass123!")
        Access.from_preset(u, role)
        self.client.force_login(u)

    def test_who_opens_what(self):
        expect = {  # page: roles that may open it
            "/staff/": {"assistant_manager"},
            "/recipes/ingredients/": {"assistant_manager", "supervisor", "admin"},
            "/sales/": {"assistant_manager", "supervisor", "admin", "cashier"},
            "/recipes/": {"assistant_manager", "supervisor", "admin", "baker"},
            "/production/": {"assistant_manager", "supervisor", "admin"},
            "/settings/": set(),  # only the Manager
            "/users/": set(),
        }
        for role in ("assistant_manager", "supervisor", "admin", "cashier", "baker"):
            self.login_as(role)
            for page, allowed in expect.items():
                code = self.client.get(page).status_code
                self.assertEqual(code == 200, role in allowed, f"{role} on {page}: {code}")
            self.client.logout()

    def test_general_manager_label(self):
        gm = User.objects.create_superuser("gm", password="TestPass123!")
        self.client.force_login(gm)
        r = self.client.get("/users/")
        self.assertContains(r, "Manager – everything")
        for label in ("Assistant Manager", "Supervisor", "Admin", "Cashier", "Baker"):
            self.assertContains(r, label)


class TickListTests(TestCase):
    def test_ticks_save(self):
        gm = User.objects.create_superuser("gm", password="TestPass123!")
        p = User.objects.create_user("sam", password="TestPass123!")
        Access.from_preset(p, "none")
        self.client.force_login(gm)
        r = self.client.get(f"/users/{p.pk}/rights/")
        for label in ("Invoices &amp; quotes", "Deliveries &amp; drivers", "Waste", "Equipment", "Can see", "Can change"):
            self.assertContains(r, label)
        # waste: see + change; invoices: only see; a "change" without "see" still counts as change
        self.client.post(f"/users/{p.pk}/rights/", {"waste_see": "on", "waste_change": "on", "invoices_see": "on",
                                                    "equipment_change": "on", "see_costs": "on"})
        a = Access.objects.get(user=p)
        self.assertEqual((a.waste, a.invoices, a.equipment, a.sales, a.see_costs), (2, 1, 2, 0, True))
        self.client.force_login(p)
        self.assertEqual(self.client.get("/production/waste/").status_code, 200)
        self.assertEqual(self.client.get("/production/").status_code, 302)   # production plans not ticked
        self.assertEqual(self.client.get("/invoices/").status_code, 200)
        self.assertEqual(self.client.get("/invoices/new/").status_code, 302)  # can see, not change
        self.assertEqual(self.client.get("/sales/").status_code, 302)
