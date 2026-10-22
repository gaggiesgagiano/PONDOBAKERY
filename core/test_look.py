import tempfile
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from costing.models import Category, Recipe

from .models import Access, CompanySettings, UserLook

FAKE_TTF = b"\x00\x01\x00\x00" + b"\x00" * 200


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LookTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.cashier = User.objects.create_user("cash", password="TestPass123!")
        Access.from_preset(self.cashier, "cashier")

    def test_default_look_and_login_page(self):
        r = self.client.get("/login/")
        self.assertContains(r, "Easy to enjoy")
        self.assertContains(r, "brand/logo/mark_cream.svg")
        self.client.login(username="owner", password="TestPass123!")
        r = self.client.get("/")
        self.assertContains(r, 'data-theme="classic"')
        self.assertContains(r, 'data-font="retro"')
        self.assertContains(r, "brand/logo/primary_reverse_cream.svg")
        self.assertContains(r, "pattern_cream.svg")

    def test_my_look_only_changes_me(self):
        self.client.login(username="cash", password="TestPass123!")
        r = self.client.post("/look/", {"theme": "night", "font": "clean", "size": "large", "pattern": "off", "greeting": ""})
        self.assertRedirects(r, "/look/", fetch_redirect_response=False)
        lk = UserLook.objects.get(user=self.cashier)
        self.assertEqual((lk.theme, lk.heading_font, lk.text_size, lk.pattern), ("night", "clean", "large", "off"))
        r = self.client.get("/")
        self.assertContains(r, 'data-theme="night"')
        self.assertContains(r, 'data-size="large"')
        self.assertContains(r, 'data-pattern="off"')
        self.assertContains(r, "primary_reverse_warm.svg")
        # nonsense is ignored, "Back to the business look" clears everything
        self.client.post("/look/", {"theme": "pink", "font": "comic"})
        lk.refresh_from_db()
        self.assertEqual((lk.theme, lk.heading_font), ("", ""))
        self.client.post("/look/", {"reset": "1"})
        self.client.logout()
        self.client.login(username="owner", password="TestPass123!")
        self.assertContains(self.client.get("/"), 'data-theme="classic"')

    def test_business_look_is_owner_only(self):
        self.client.login(username="cash", password="TestPass123!")
        self.client.post("/settings/look/", {"theme": "teal", "font": "round", "size": "normal", "pattern": "on"})
        self.assertEqual(CompanySettings.get().theme, "classic")
        self.client.logout()
        self.client.login(username="owner", password="TestPass123!")
        self.assertEqual(self.client.get("/settings/look/").status_code, 200)
        self.client.post("/settings/look/", {"theme": "teal", "font": "round", "size": "xl", "greeting": "on", "tagline": "Pondo yako chete!"})
        cs = CompanySettings.get()
        self.assertEqual((cs.theme, cs.heading_font, cs.text_size, cs.pattern, cs.greeting, cs.tagline),
                         ("teal", "round", "xl", False, True, "Pondo yako chete!"))
        self.client.logout()
        self.assertContains(self.client.get("/login/"), "Pondo yako chete!")
        self.client.login(username="cash", password="TestPass123!")
        self.assertContains(self.client.get("/"), 'data-theme="teal"')

    def test_pondo_font_upload(self):
        self.client.login(username="owner", password="TestPass123!")
        # the Pondo font can't be chosen before it is added
        self.client.post("/look/", {"font": "pondo"})
        self.assertNotContains(self.client.get("/"), 'data-font="pondo"')
        bad = SimpleUploadedFile("pondo.ttf", b"this is not a font")
        self.client.post("/settings/look/font/", {"font": bad})
        self.assertEqual(CompanySettings.get().brand_font, "")
        ok = SimpleUploadedFile("RetroStar.ttf", FAKE_TTF)
        self.client.post("/settings/look/font/", {"font": ok})
        cs = CompanySettings.get()
        self.assertEqual((cs.brand_font, cs.heading_font), ("pondo-font.ttf", "pondo"))
        r = self.client.get("/")
        self.assertContains(r, 'data-font="pondo"')
        self.assertContains(r, "@font-face{font-family:\"Pondo Brand\"")
        self.client.logout()
        r = self.client.get("/brand/font/")  # the log-in page needs it too
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "font/ttf")
        self.assertEqual(b"".join(r.streaming_content), FAKE_TTF)
        self.client.login(username="owner", password="TestPass123!")
        self.client.post("/settings/look/font/", {"remove": "1"})
        cs = CompanySettings.get()
        self.assertEqual((cs.brand_font, cs.heading_font), ("", "retro"))
        self.assertEqual(self.client.get("/brand/font/").status_code, 404)

    def test_brand_page(self):
        self.client.login(username="cash", password="TestPass123!")
        r = self.client.get("/brand/")
        self.assertContains(r, "#e56026")
        self.assertContains(r, "7579 C")
        self.assertContains(r, "brand/png/primary_burgundy.png")
        self.assertContains(r, "Burgundy badge on a cream circle")
        self.assertContains(r, "Retro Star")


class PriceCardTests(TestCase):
    def setUp(self):
        User.objects.create_superuser("owner", password="TestPass123!")
        self.client.login(username="owner", password="TestPass123!")
        cakes = Category.objects.create(name="Cakes")
        pies = Category.objects.create(name="Pies")
        self.ids = []
        for n in range(30):
            r = Recipe.objects.create(number=900 + n, name=f"Chicken Pie {n}" if n % 2 else f"Cake {n}",
                                      category=pies if n % 2 else cakes, sell_price=D("1.80") + n)
            self.ids.append(r.pk)
        Recipe.objects.create(number=999, name="No price", category=cakes)

    def test_pick_page_lists_priced_products(self):
        r = self.client.get("/recipes/prices/cards/")
        self.assertContains(r, "Cake 0")
        self.assertNotContains(r, "No price")

    def test_layouts(self):
        q = "&".join(f"p={i}" for i in self.ids)
        r = self.client.get(f"/recipes/prices/cards/print/?layout=shelf&style=mix&only=1&{q}")
        self.assertEqual(r.content.decode().count('class="page shelf"'), 4)  # 30 cards, 8 a page
        self.assertContains(r, "$1.80")
        for style in ("orange", "burgundy", "teal", "warm", "cream"):  # the mix uses every brand colour
            self.assertContains(r, f'class="pc {style}')
        r = self.client.get(f"/recipes/prices/cards/print/?layout=big&style=cream&photos=1&{q}")
        self.assertEqual(r.content.decode().count('class="page big"'), 8)
        self.assertContains(r, "art/pie_cream.svg")  # no photo -> the pie illustration in the picture window
        r = self.client.get(f"/recipes/prices/cards/print/?layout=poster&style=teal&head=Fresh+today&{q}")
        self.assertEqual(r.content.decode().count('class="page poster"'), 30)
        self.assertContains(r, "Fresh today")
        r = self.client.get(f"/recipes/prices/cards/print/?layout=menu&style=burgundy&{q}")
        self.assertContains(r, "Price<br>list")
        self.assertContains(r, "Chicken Pie 29")
        r = self.client.get("/recipes/prices/cards/print/?layout=big")
        self.assertContains(r, "Nothing chosen")


class BrandEverywhereTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.cashier = User.objects.create_user("cash", password="TestPass123!")
        Access.from_preset(self.cashier, "cashier")

    def test_area_colours_menu_and_help(self):
        self.client.login(username="owner", password="TestPass123!")
        r = self.client.get("/sales/cashups/")
        self.assertContains(r, 'class="c-teal" data-area="sales"')
        self.assertContains(r, "brand/art/cookie_cream.svg")       # the area illustration in the header band
        self.assertContains(r, "/manual/#sales")                     # help for this page
        self.assertContains(r, "Tax &amp; Compliance")               # menu groups
        self.assertContains(r, 'class="nav c-teal on"')
        r = self.client.get("/production/")
        self.assertContains(r, 'class="c-warm" data-area="production"')
        self.assertContains(r, "bread_burgundy.svg")                 # warm orange band takes burgundy (reverse colours)
        r = self.client.get("/recipes/ingredients/")
        self.assertContains(r, 'data-area="ingredients"')
        self.assertContains(r, "submark_orange.svg")                 # page footer badge

    def test_menu_follows_rights(self):
        self.client.login(username="cash", password="TestPass123!")
        r = self.client.get("/")
        self.assertContains(r, "Sales &amp; Cash-Up")
        self.assertNotContains(r, "Staff &amp; Payroll")
        self.assertNotContains(r, ">Settings<")
        self.assertContains(r, "Short Cuts")
        self.assertContains(r, "Type the day&#x27;s sales")
        self.assertNotContains(r, "Production plan")

    def test_jobs_done_and_to_do(self):
        import datetime
        from django.utils import timezone

        from sales.models import DailySales
        self.client.login(username="owner", password="TestPass123!")
        r = self.client.get("/").content.decode()
        jobs = r[r.index('<div class="jobs">'):]
        i = jobs.index("Type the day&#x27;s sales")
        self.assertNotIn("done", jobs[jobs.rindex("<a ", 0, i):i])
        DailySales.objects.create(date=timezone.localdate(), total=100, gp_amount=50)
        r = self.client.get("/").content.decode()
        jobs = r[r.index('<div class="jobs">'):]
        i = jobs.index("Type the day&#x27;s sales")
        self.assertIn("job c-teal done", jobs[jobs.rindex("<a ", 0, i):i])

    def test_manual(self):
        self.client.login(username="cash", password="TestPass123!")
        r = self.client.get("/manual/")
        self.assertContains(r, "Staff manual")
        self.assertContains(r, 'id="sales"')
        self.assertNotContains(r, 'id="staff"')        # a cashier gets their own chapters
        r = self.client.get("/manual/?role=all")
        self.assertContains(r, 'id="staff"')
        self.assertContains(r, 'id="glossary"')
        r = self.client.get("/manual/print/?role=baker")
        self.assertContains(r, "Staff<br>manual")
        self.assertContains(r, "Baker")
        self.assertContains(r, "Recipes &amp; Prices")
        self.assertNotContains(r, "Cash up every till")
        r = self.client.get("/manual/print/?ch=sales&ink=low")
        self.assertContains(r, "Cash up every till")
        self.assertNotContains(r, 'class="cover"')

    def test_friendly_404(self):
        self.client.login(username="owner", password="TestPass123!")
        r = self.client.get("/no-such-page/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Page not found", status_code=404)
