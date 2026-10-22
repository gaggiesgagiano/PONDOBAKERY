from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase

from core.models import Access
from costing.models import Ingredient, Recipe, RecipeLine

from .models import PlanLine, ProductionPlan, WasteLog
from .plan_calc import PlanResult


class ProductionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        self.flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("1"))
        self.bag = Ingredient.objects.create(name="Bag", unit="each", pack_size=1, pack_price=D("0.05"), kind=Ingredient.PACKAGING)
        self.sugar = Ingredient.objects.create(name="Sugar", unit="kg", pack_size=1, pack_price=D("2"))
        # mother recipe: 10 kg dough, 50% loss -> 5 kg custard
        self.custard = Recipe.objects.create(number=900, name="Custard", is_subrecipe=True, weight_loss=D("0.5"))
        RecipeLine.objects.create(recipe=self.custard, ingredient=self.sugar, qty=10)
        self.custard_ing = Ingredient.objects.create(name="Custard", kind=Ingredient.SUBRECIPE, unit="kg", recipe=self.custard)
        # loaf: 10 kg flour, 0.5 kg each -> 20 loaves; 0.1 kg custard per loaf; 1 bag per loaf
        self.loaf = Recipe.objects.create(number=1, name="Loaf", scaling_weight=D("0.5"), par_day=30, sell_price=D("2"))
        RecipeLine.objects.create(recipe=self.loaf, ingredient=self.flour, qty=10)
        RecipeLine.objects.create(recipe=self.loaf, ingredient=self.custard_ing, qty=D("0.1"), qty_mode=RecipeLine.PER_UNIT,
                                  section=RecipeLine.TOPPING)
        RecipeLine.objects.create(recipe=self.loaf, ingredient=self.bag, qty=1, qty_mode=RecipeLine.PER_UNIT,
                                  section=RecipeLine.PACKAGING)

    def test_plan_maths_and_explosion(self):
        plan = ProductionPlan.objects.create(date="2026-10-10", shift="day")
        PlanLine.objects.create(plan=plan, recipe=self.loaf, model_stock=30, on_hand=12, expired=2)
        res = PlanResult(plan)
        p = res.products[0]
        self.assertEqual(p["units"], 20)                 # 30 - (12-2)
        self.assertEqual(p["batches"], D("1"))           # 20 / yield 20
        ing = {d["ingredient"].name: d["qty"] for d in res.ingredient_rows}
        self.assertEqual(ing["Flour"], D("10"))
        self.assertEqual(ing["Bag"], D("20"))
        self.assertEqual(ing["Sugar"], D("4"))           # 2 kg custard needed = 0.4 batch of 10 kg sugar
        prep = res.prepare_rows[0]
        self.assertEqual((prep["recipe"].name, prep["qty"]), ("Custard", D("2")))
        self.assertEqual(res.total_cost, D("10") + D("1") + D("8"))

    def test_new_plan_from_model_stock_and_edit(self):
        r = self.client.post("/production/new/", {"date": "2026-10-10", "shift": "day", "start": "model"})
        plan = ProductionPlan.objects.get()
        self.assertRedirects(r, f"/production/{plan.pk}/edit/", fetch_redirect_response=False)
        self.assertEqual(plan.lines.get().model_stock, 30)
        data = {"supervisor": "Sydney", "status": "final", "notes": "",
                "ln-TOTAL_FORMS": "1", "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000",
                "ln-0-product": "loaf", "ln-0-model_stock": "30", "ln-0-on_hand": "5", "ln-0-expired": "", "ln-0-actual": "40"}
        self.assertEqual(self.client.post(f"/production/{plan.pk}/edit/", data).status_code, 302)
        self.assertEqual(plan.lines.get().units, 40)
        for kind in ("sheet", "pull", "cards"):
            self.assertEqual(self.client.get(f"/production/{plan.pk}/print/{kind}/").status_code, 200, kind)
        page = self.client.get(f"/production/{plan.pk}/")
        self.assertContains(page, "Prepare first")
        # second plan for same date/shift refused
        r2 = self.client.post("/production/new/", {"date": "2026-10-10", "shift": "day", "start": "empty"})
        self.assertContains(r2, "already a plan")

    def test_waste_log_cost_snapshot_and_summary(self):
        self.client.post("/production/waste/new/", {"date": "2026-10-09", "shift": "day"})
        w = WasteLog.objects.get()
        data = {"notes": "", "ln-TOTAL_FORMS": "2", "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000",
                "ln-0-product": "Loaf", "ln-0-qty": "4", "ln-0-reason": "Expired", "ln-0-notes": "",
                "ln-1-product": "", "ln-1-qty": "", "ln-1-reason": "Expired", "ln-1-notes": ""}
        self.assertEqual(self.client.post(f"/production/waste/{w.pk}/edit/", data).status_code, 302)
        ln = w.lines.get()
        self.assertEqual(ln.unit_cost, D("0.95"))   # ($10 flour + $8 custard + $1 bags) / 20 loaves
        self.assertEqual(w.total_cost, D("3.80"))
        self.assertContains(self.client.get("/production/waste/summary/?month=2026-10"), "$3.80")
        self.client.post(f"/production/waste/{w.pk}/signoff/")
        w.refresh_from_db()
        self.assertEqual(w.signed_off_by, self.owner)

    def test_rights(self):
        cash = User.objects.create_user("cash", password="TestPass123!")
        Access.from_preset(cash, "cashier")
        baker = User.objects.create_user("baker", password="TestPass123!")
        Access.from_preset(baker, "baker")
        self.client.logout()
        self.client.login(username="cash", password="TestPass123!")
        self.assertEqual(self.client.get("/production/").status_code, 302)
        self.client.logout()
        self.client.login(username="baker", password="TestPass123!")
        self.assertEqual(self.client.get("/production/").status_code, 302)  # a baker only has recipes
        self.assertEqual(self.client.get("/recipes/").status_code, 200)
        self.assertEqual(self.client.get("/production/waste/summary/").status_code, 302)
