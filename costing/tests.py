import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from core.models import ChangeLog
from costing.calc import Calculator
from costing.models import Category, Ingredient, IngredientPriceChange, Recipe, RecipeLine

XLSX = os.environ.get("PONDO_TEST_XLSX", "/home/claude/PB_Master_File.xlsx")


def D(x):
    return Decimal(str(x))


class CostingMaths(TestCase):
    def setUp(self):
        self.bread = Category.objects.create(name="Bread")
        self.flour = Ingredient.objects.create(name="White Bread Flour", unit="kg", pack_size=1, pack_price=D("0.75"))
        self.yeast = Ingredient.objects.create(name="Fresh Yeast", unit="kg", pack_size=1, pack_price=D("1.68"))
        self.bag = Ingredient.objects.create(name="Bread Bags", unit="each", pack_size=1, pack_price=D("0.03"),
                                             kind=Ingredient.PACKAGING)
        self.r = Recipe.objects.create(number=201001, name="White Bread 600g", category=self.bread,
                                       scaling_weight=D("0.65"), sell_price=D("1.00"), vat_rate=D("0"))
        RecipeLine.objects.create(recipe=self.r, ingredient=self.flour, qty=D("47"), position=1)
        RecipeLine.objects.create(recipe=self.r, ingredient=self.yeast, qty=D("0.94"), position=2)
        RecipeLine.objects.create(recipe=self.r, ingredient=self.bag, qty=1, qty_mode=RecipeLine.PER_UNIT,
                                  section=RecipeLine.PACKAGING, position=3)

    def test_yield_and_cost(self):
        c = Calculator()
        self.assertEqual(c.dough_weight(self.r), D("47.94"))
        self.assertEqual(c.batch_yield(self.r), 73)  # floor(47.94 / 0.65)
        expected = D("47") * D("0.75") + D("0.94") * D("1.68") + 73 * D("0.03")
        self.assertEqual(c.batch_cost(self.r), expected)
        self.assertAlmostEqual(float(c.cost_per_unit(self.r)), float(expected / 73), places=9)

    def test_gp_and_target_price(self):
        c = Calculator()
        cpu = c.cost_per_unit(self.r)
        self.assertAlmostEqual(float(c.gp(self.r)), float((1 - cpu) / 1), places=9)
        self.assertAlmostEqual(float(c.target_price(self.r, D("0.6"))), float(cpu / D("0.4")), places=9)

    def test_vat_in_pack_price(self):
        oil = Ingredient.objects.create(name="Oil", unit="L", pack_size=20, pack_price=D("23.10"), vat_rate=D("0.155"))
        self.assertAlmostEqual(float(Calculator().unit_cost(oil)), 1.0, places=9)

    def test_weight_loss_reduces_yield(self):
        self.r.weight_loss = D("0.10")
        self.r.save()
        self.assertEqual(Calculator().batch_yield(self.r), 66)  # floor(47.94*0.9/0.65)

    def test_mother_recipe_priced_per_finished_kg(self):
        filling = Recipe.objects.create(number=201350, name="Filling", is_subrecipe=True, weight_loss=D("0.5"))
        RecipeLine.objects.create(recipe=filling, ingredient=self.flour, qty=D("10"))
        ing = Ingredient.objects.create(name="Filling", kind=Ingredient.SUBRECIPE, unit="kg", recipe=filling)
        c = Calculator()
        self.assertEqual(c.unit_cost(ing), D("7.5") / D("5"))  # $7.50 over 5 kg finished

    def test_cycle_is_caught(self):
        from costing.calc import CycleError

        a = Recipe.objects.create(number=1, name="A", is_subrecipe=True)
        ing_a = Ingredient.objects.create(name="A", kind=Ingredient.SUBRECIPE, unit="kg", recipe=a)
        RecipeLine.objects.create(recipe=a, ingredient=ing_a, qty=1)
        with self.assertRaises(CycleError):
            Calculator().batch_cost(a)


class Screens(TestCase):
    def setUp(self):
        self.u = User.objects.create_superuser("gaggies", password="TestPass123!")
        self.client.login(username="gaggies", password="TestPass123!")
        self.flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=25, pack_price=D("20"))

    def _post_recipe(self, name, lines, pk=None, **extra):
        data = {"name": name, "number": extra.get("number", 201500), "scaling_weight": "0.5", "active": "on",
                "ln-TOTAL_FORMS": str(len(lines)), "ln-INITIAL_FORMS": "0", "ln-MIN_NUM_FORMS": "0", "ln-MAX_NUM_FORMS": "1000"}
        data.update({k: v for k, v in extra.items() if k != "number"})
        for i, (sec, ing, qty, mode) in enumerate(lines):
            data.update({f"ln-{i}-section": sec, f"ln-{i}-ingredient": ing, f"ln-{i}-qty": qty, f"ln-{i}-qty_mode": mode})
        url = f"/recipes/{pk}/edit/" if pk else "/recipes/new/"
        return self.client.post(url, data)

    def test_first_start_goes_to_setup(self):
        self.client.logout()
        User.objects.all().delete()
        from core import middleware

        r = self.client.get("/recipes/")
        self.assertRedirects(r, "/setup/", fetch_redirect_response=False)

    def test_login_required(self):
        self.client.logout()
        r = self.client.get("/recipes/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_create_recipe_and_cost(self):
        r = self._post_recipe("Test Loaf", [("dough", "flour", "10", "fixed"), ("dough", "", "", "fixed")])
        self.assertEqual(r.status_code, 302, r.content[:2000])
        rec = Recipe.objects.get(name="Test Loaf")
        self.assertEqual(rec.lines.count(), 1)
        self.assertEqual(Calculator().batch_cost(rec), D("8"))  # 10 kg × $0.80
        self.assertTrue(ChangeLog.objects.filter(item="Test Loaf").exists())
        page = self.client.get(f"/recipes/{rec.pk}/")
        self.assertContains(page, "$8.00")

    def test_unknown_ingredient_is_refused(self):
        r = self._post_recipe("Bad", [("dough", "Unicorn dust", "1", "fixed")])
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "not on the ingredient list")
        self.assertFalse(Recipe.objects.filter(name="Bad").exists())

    def test_mother_recipe_appears_as_ingredient(self):
        self._post_recipe("Custard", [("dough", "Flour", "5", "fixed")], is_subrecipe="on")
        rec = Recipe.objects.get(name="Custard")
        ing = Ingredient.objects.get(recipe=rec)
        self.assertEqual(ing.kind, Ingredient.SUBRECIPE)
        self.assertAlmostEqual(float(Calculator().unit_cost(ing)), 0.8, places=9)

    def test_price_change_is_recorded(self):
        r = self.client.post(f"/recipes/ingredients/{self.flour.pk}/edit/", {
            "name": "Flour", "kind": "bought", "unit": "kg", "pack_size": "25", "pack_price": "25", "active": "on"})
        self.assertEqual(r.status_code, 302)
        ch = IngredientPriceChange.objects.get(ingredient=self.flour)
        self.assertEqual((ch.old_price, ch.new_price), (D("20"), D("25")))

    def test_bulk_price_edit(self):
        rec = Recipe.objects.create(number=5, name="Bun", scaling_weight=D("1"))
        r = self.client.post("/recipes/prices/", {f"p{rec.pk}": "2.50"})
        self.assertEqual(r.status_code, 302)
        rec.refresh_from_db()
        self.assertEqual(rec.sell_price, D("2.50"))


class ExcelImport(TestCase):
    def test_import_matches_excel(self):
        if not os.path.exists(XLSX):
            self.skipTest("master Excel file not available")
        from io import StringIO

        out = StringIO()
        call_command("import_excel", XLSX, stdout=out)
        text = out.getvalue()
        self.assertGreater(Recipe.objects.count(), 300)
        self.assertGreater(Ingredient.objects.count(), 300)
        wb = Recipe.objects.get(name="White Bread 600g")
        self.assertAlmostEqual(float(Calculator().batch_cost(wb)), 46.153, places=3)
        # Only the known Excel fault (Breakfast Rolls: Garlic Oil left out of the dough weight) may differ
        self.assertIn("Breakfast Rolls 80g", text)
        self.assertIn("1 recipe(s) cost differently", text)


class Rights(TestCase):
    def setUp(self):
        from core.models import Access

        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.baker = User.objects.create_user("baker", password="TestPass123!")
        Access.from_preset(self.baker, "baker")
        self.cashier = User.objects.create_user("cash", password="TestPass123!")
        Access.from_preset(self.cashier, "cashier")
        flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=D("0.75"))
        self.r = Recipe.objects.create(number=1, name="Loaf", scaling_weight=D("1"), sell_price=D("2.00"))
        RecipeLine.objects.create(recipe=self.r, ingredient=flour, qty=D("10"))

    def test_baker_sees_recipe_without_costs(self):
        self.client.login(username="baker", password="TestPass123!")
        self.assertEqual(self.client.get("/").status_code, 200)
        page = self.client.get(f"/recipes/{self.r.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Flour")
        self.assertNotContains(page, "$7.50")  # batch cost hidden
        self.assertNotContains(page, "Gross profit")
        self.assertRedirects(self.client.get(f"/recipes/{self.r.pk}/edit/"), "/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/recipes/prices/"), "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(f"/recipes/{self.r.pk}/print/costing/").status_code, 302)
        self.assertEqual(self.client.get("/settings/").status_code, 302)

    def test_cashier_prices_only(self):
        self.client.login(username="cash", password="TestPass123!")
        page = self.client.get("/recipes/prices/")
        self.assertContains(page, "$2.00")
        self.assertNotContains(page, "GP %")
        self.assertEqual(self.client.get("/recipes/").status_code, 302)
        self.client.post("/recipes/prices/", {f"p{self.r.pk}": "9.99"})
        self.r.refresh_from_db()
        self.assertEqual(self.r.sell_price, D("2.00"))  # view-only cannot change

    def test_owner_sets_custom_rights(self):
        self.client.login(username="owner", password="TestPass123!")
        for url in ("/", "/users/", f"/users/{self.baker.pk}/rights/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        data = {"recipes_see": "on", "recipes_change": "on", "prices_see": "on", "see_costs": "on"}  # the tick list
        self.assertEqual(self.client.post(f"/users/{self.baker.pk}/rights/", data).status_code, 302)
        self.baker.access.refresh_from_db()
        self.assertEqual((self.baker.access.recipes, self.baker.access.see_costs, self.baker.access.role), (2, True, "custom"))
        self.client.logout()
        self.client.login(username="baker", password="TestPass123!")
        self.assertEqual(self.client.get(f"/recipes/{self.r.pk}/edit/").status_code, 200)


class SoldPerKgTests(TestCase):
    def test_kg_products(self):
        from django.contrib.auth.models import User
        from stock.models import StockCount
        self.assertEqual(Recipe.guess_sold_per("Aniseed Rusks p/kg"), "kg")
        self.assertEqual(Recipe.guess_sold_per("Tea Biscuits per kg"), "kg")
        self.assertEqual(Recipe.guess_sold_per("Party Bread 1,8kg"), "each")
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        rusk = Recipe.objects.create(number=1, name="Aniseed Rusks p/kg", sold_per="kg", sell_price=Decimal("8.90"))
        Recipe.objects.create(number=2, name="Brownies Each", sell_price=Decimal("0.60"))
        self.assertContains(self.client.get("/recipes/prices/", follow=True), "p/kg")
        r = self.client.get(f"/recipes/prices/cards/print/?layout=shelf&p={rusk.pk}")
        self.assertContains(r, "$8.90")
        self.assertNotContains(r, "per kg")  # the name already says p/kg
        c = StockCount.objects.create(date="2026-10-09")
        sheet = self.client.get(f"/stock/counts/{c.pk}/sheet/").content.decode()
        row = sheet[sheet.index("Aniseed Rusks p/kg"):][:300]
        self.assertIn("<td>kg</td>", row)
        row = sheet[sheet.index("Brownies Each"):][:300]
        self.assertIn("<td>each</td>", row)


class RecipeNumberTests(TestCase):
    def test_free_numbers_in_list_and_form(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        for n in (201001, 201002, 201005, 201009):
            Recipe.objects.create(number=n, name=f"R{n}")
        r = self.client.get("/recipes/")
        s = r.content.decode()
        # in number order, every free number stays as an empty line in its place
        self.assertLess(s.index("R201002"), s.index("?number=201003"))
        self.assertLess(s.index("?number=201004"), s.index("R201005"))
        self.assertContains(r, "?number=201006")
        self.assertContains(r, "Recipes &amp; Prices")
        self.assertContains(r, "<b>999</b> recipes")
        r = self.client.get("/recipes/new/?number=201007")
        self.assertContains(r, 'value="201007"')
        self.assertContains(r, 'data-num="201003"')
        r = self.client.get("/recipes/?q=R2010")          # a search shows no gap rows
        self.assertNotContains(r, "?number=")


class GPRangeTests(TestCase):
    def test_gp_range_shows_only_those_products(self):
        from django.contrib.auth.models import User
        from unittest import mock
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        a = Recipe.objects.create(number=201001, name="Low GP", sell_price=Decimal("1.00"))
        b = Recipe.objects.create(number=201002, name="Mid GP", sell_price=Decimal("1.00"))
        c = Recipe.objects.create(number=201004, name="High GP", sell_price=Decimal("1.00"))
        gps = {a.pk: Decimal("0.30"), b.pk: Decimal("0.55"), c.pk: Decimal("0.70")}
        from costing.calc import Calculator
        real = Calculator.summary
        def fake(self, r):
            s = real(self, r); s["gp"] = gps.get(r.pk, s["gp"]); return s
        with mock.patch.object(Calculator, "summary", fake):
            s = self.client.get("/recipes/?gp_max=49.99").content.decode()
            self.assertIn("Low GP", s); self.assertNotIn("Mid GP", s); self.assertNotIn("High GP", s)
            self.assertNotIn("?number=201003", s)          # no empty lines in a GP check
            s = self.client.get("/recipes/?gp_min=50&gp_max=59.99").content.decode()
            self.assertIn("Mid GP", s); self.assertNotIn("Low GP", s)
            self.assertIn("<b>1</b> product", s)
            # saving a price keeps the GP range
            r = self.client.post("/recipes/?gp_max=49.99", {f"p{a.pk}": "2.00"})
            self.assertIn("gp_max=49.99", r["Location"])
        self.assertIn("?gp_max=49.99", self.client.get("/").content.decode())  # GP check in the menu
