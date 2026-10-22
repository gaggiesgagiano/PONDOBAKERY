"""Open an edit page and press Save without changing anything: it must save.

A recipe with VAT 15% showed "15.0000" in the VAT box, and saving then failed with
"Ensure that there are no more than 3 decimal places." – so a new selling price never saved.
"""
from decimal import Decimal
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase

from core.access import Rights
from core.jobs import chosen
from core.models import Access, ChangeLog, CompanySettings
from costing.models import Category, Ingredient, Recipe, RecipeLine


class _Form(HTMLParser):
    """What a browser would send back: every box of the biggest form on the page, as it is."""

    def __init__(self):
        super().__init__()
        self.forms, self.cur, self.sel, self.ta, self.skip = [], None, None, None, 0

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "form" and (a.get("method") or "").lower() == "post":
            self.cur = {"action": a.get("action") or "", "data": [], "n": 0}
            self.forms.append(self.cur)
            return
        if self.cur is None:
            return
        if tag == "template":
            self.skip += 1
        if self.skip:
            return
        if tag == "input" and a.get("name"):
            t = a.get("type", "text")
            self.cur["n"] += 1
            if t in ("checkbox", "radio"):
                if "checked" in a:
                    self.cur["data"].append((a["name"], a.get("value", "on")))
            elif t not in ("file", "submit", "button"):
                self.cur["data"].append((a["name"], a.get("value", "")))
        elif tag == "select":
            self.sel, self.first, self.picked = a.get("name"), None, False
            self.cur["n"] += 1
        elif tag == "option" and self.sel:
            if self.first is None:
                self.first = a.get("value", "")
            if "selected" in a:
                self.cur["data"].append((self.sel, a.get("value", "")))
                self.picked = True
        elif tag == "textarea":
            self.ta, self.tav = a.get("name"), ""
            self.cur["n"] += 1

    def handle_endtag(self, tag):
        if tag == "template" and self.skip:
            self.skip -= 1
        if tag == "form":
            self.cur = None
        if tag == "select" and self.sel and self.cur is not None:
            if not self.picked and self.first is not None:
                self.cur["data"].append((self.sel, self.first))
            self.sel = None
        if tag == "textarea" and self.ta and self.cur is not None:
            self.cur["data"].append((self.ta, self.tav[1:] if self.tav.startswith("\n") else self.tav))
            self.ta = None

    def handle_data(self, d):
        if self.ta:
            self.tav += d


def page_form(client, url):
    p = _Form()
    p.feed(client.get(url).content.decode())
    f = max((f for f in p.forms if "logout" not in f["action"]), key=lambda f: f["n"])
    data = {}
    for k, v in f["data"]:
        data.setdefault(k, []).append(v)
    return data


class SaveAsItIs(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(self.owner)
        cat = Category.objects.create(name="Cakes")
        self.flour = Ingredient.objects.create(name="Flour", unit="kg", pack_size=1, pack_price=Decimal("0.75"))
        r = Recipe.objects.create(number=211, name='10" Square', category=cat, scaling_weight=Decimal("1.2"),
                                  sell_price=Decimal("23.80"), vat_rate=Decimal("0.15"), weight_loss=Decimal("0.1"),
                                  bake_time="4-5 folds, 20-30 min rest between folds; final rest 1 h (overnight best)")
        RecipeLine.objects.create(recipe=r, ingredient=self.flour, qty=Decimal("1.2345"))
        self.r = Recipe.objects.get(pk=r.pk)  # as it comes from the database: 0.1500, 0.1000

    def test_recipe_price_change_saves(self):
        url = f"/recipes/{self.r.pk}/edit/"
        page = self.client.get(url).content.decode()
        self.assertIn('name="vat_percent" value="15"', page)
        self.assertIn('name="loss_percent" value="10"', page)
        data = page_form(self.client, url)
        data["sell_price"] = ["24.50"]
        r = self.client.post(url, data)
        self.assertRedirects(r, f"/recipes/{self.r.pk}/", fetch_redirect_response=False)
        self.r.refresh_from_db()
        self.assertEqual(self.r.sell_price, Decimal("24.50"))
        self.assertEqual(self.r.vat_rate, Decimal("0.15"))
        self.assertEqual(self.r.weight_loss, Decimal("0.1"))
        self.assertEqual(self.r.lines.get().qty, Decimal("1.2345"))
        self.assertTrue(ChangeLog.objects.filter(area="Prices", item='10" Square', details="23.80 → 24.50").exists())

    def test_typed_zeros_do_not_count(self):
        url = f"/recipes/{self.r.pk}/edit/"
        data = page_form(self.client, url)
        data["vat_percent"] = ["15.0000"]
        data["loss_percent"] = ["12.50000"]
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.r.refresh_from_db()
        self.assertEqual(self.r.weight_loss, Decimal("0.125"))

    def test_error_is_shown_at_the_top(self):
        url = f"/recipes/{self.r.pk}/edit/"
        data = page_form(self.client, url)
        data["loss_percent"] = ["12.12345"]
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="field bad"')

    def test_ingredient_made_from_a_product_saves(self):
        crumbs = Ingredient.objects.create(name="Bread Crumbs", kind=Ingredient.SUBRECIPE, unit="kg", recipe=self.r)
        url = f"/recipes/ingredients/{crumbs.pk}/edit/"
        r = self.client.post(url, page_form(self.client, url))
        self.assertEqual(r.status_code, 302)
        crumbs.refresh_from_db()
        self.assertEqual(crumbs.recipe, self.r)

    def test_settings_save(self):
        cs = CompanySettings.get()
        cs.vat_rate, cs.target_gp, cs.gp_low = Decimal("0.155"), Decimal("0.6"), Decimal("0.45")
        cs.save()
        r = self.client.post("/settings/", page_form(self.client, "/settings/"))
        self.assertEqual(r.status_code, 302)
        cs = CompanySettings.get()
        self.assertEqual(cs.vat_rate, Decimal("0.155"))
        r = self.client.post("/settings/costs/", page_form(self.client, "/settings/costs/"))
        self.assertEqual(r.status_code, 302)


class PriceJob(TestCase):
    def test_change_prices_on_todays_jobs(self):
        owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(owner)
        Recipe.objects.create(number=1, name="Loaf", sell_price=None)
        html = self.client.get("/").content.decode()
        self.assertIn("Change prices", html)
        self.assertIn('href="/recipes/prices/?edit=1"', html)
        self.assertIn("1 product without a price", html)
        self.assertIn("price_change", chosen(Rights(owner), owner))
        # somebody who chose their jobs before Change prices existed gets it next to Price cards
        from core.models import UserLook

        UserLook.objects.update_or_create(user=owner, defaults={"jobs": "sales,cashup,prices,backup,!low_stock"})
        keys = chosen(Rights(owner), owner)
        self.assertEqual(keys.index("price_change") + 1, keys.index("prices"))
        self.assertEqual([k for k in keys if k in ("sales", "cashup", "prices", "backup")][:2], ["sales", "cashup"])  # saved order kept
        self.assertContains(self.client.get("/jobs/"), "Change prices")
        till = User.objects.create_user("till", password="x")
        Access.from_preset(till, "cashier")
        self.assertNotIn("price_change", chosen(Rights(till), till))  # may not change prices


class PriceListComesBack(TestCase):
    def test_after_saving_the_same_search_and_line_stay(self):
        owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(owner)
        r = Recipe.objects.create(number=1, name='10" Square', sell_price=Decimal("23.80"))
        r2 = Recipe.objects.create(number=2, name="Loaf", sell_price=None)
        url = "/recipes/?show=noprice&q=loaf"   # Recipes & Prices: prices are typed straight into the list
        resp = self.client.post(url, {f"p{r2.pk}": "1.20", "at": f"p{r2.pk}"})
        self.assertEqual(resp.status_code, 302)
        back = resp["Location"]
        for part in ("show=noprice", "q=loaf", f"saved={r2.pk}", f"at=p{r2.pk}"):
            self.assertIn(part, back)
        page = self.client.get(back)
        self.assertContains(page, "Saved Loaf – $1.20.")
        html = page.content.decode()
        self.assertIn('value="loaf"', html)
        self.assertIn("✓ saved", html)
        self.assertIn(f'id="p{r2.pk}"', html)  # still on the "No price" list, although it has a price now
        self.assertNotIn(f'id="p{r.pk}"', html)
        fresh = self.client.get("/recipes/?show=noprice").content.decode()
        self.assertNotIn(f'id="p{r2.pk}"', fresh)  # coming back later: starts again
        self.assertNotIn("✓ saved", fresh)
        # the old address still works and lands on the combined page
        self.assertRedirects(self.client.get("/recipes/prices/?f=low"), "/recipes/?show=low", fetch_redirect_response=False)
