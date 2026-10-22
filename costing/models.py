import re
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Supplier(models.Model):
    name = models.CharField(max_length=80, unique=True)
    company_name = models.CharField(max_length=120, blank=True)
    contact = models.CharField("Contact person", max_length=120, blank=True)
    phone = models.CharField("Cell / phone", max_length=60, blank=True)
    email = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=200, blank=True)
    account_no = models.CharField("Our account no.", max_length=60, blank=True)
    terms_days = models.PositiveSmallIntegerField("Payment terms (days)", default=0,
                                                  help_text="0 = we pay on delivery. 30 = we pay within 30 days of the invoice.")
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


UNIT_CHOICES = [("kg", "kg"), ("L", "litre"), ("each", "each"), ("sheet", "sheet"), ("m", "metre")]
WEIGHT_UNITS = ("kg", "L")


class Ingredient(models.Model):
    BOUGHT, PACKAGING, SUBRECIPE = "bought", "packaging", "subrecipe"
    KIND_CHOICES = [(BOUGHT, "Ingredient (bought)"), (PACKAGING, "Packaging (bought)"),
                    (SUBRECIPE, "Mother recipe (made here)")]

    name = models.CharField(max_length=150, unique=True)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=BOUGHT)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="ingredients", verbose_name="Supplier / group")
    code = models.CharField("Product code", max_length=40, blank=True)
    unit = models.CharField(max_length=6, choices=UNIT_CHOICES, default="kg",
                            help_text="The unit you use in recipes")
    pack_size = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("1"),
                                    help_text="How many units are in the pack you buy, e.g. 25 for a 25 kg bag")
    pack_price = models.DecimalField("Pack price ($)", max_digits=12, decimal_places=4, null=True, blank=True,
                                     help_text="What you pay for one pack, as on the invoice")
    vat_rate = models.DecimalField("VAT in pack price", max_digits=6, decimal_places=4, default=Decimal("0"),
                                   help_text="0 if the price has no VAT you can claim back; 0.155 if it includes 15.5% VAT")
    recipe = models.OneToOneField("Recipe", null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="as_ingredient",
                                  help_text="For mother recipes: the recipe that makes this")
    reorder_level = models.DecimalField("Re-order when stock is below", max_digits=12, decimal_places=3, null=True,
                                        blank=True, help_text="In the recipe unit (kg, litre, each)")
    stock_par = models.DecimalField("Order up to", max_digits=12, decimal_places=3, null=True, blank=True,
                                    help_text="How much you want in the store after a delivery")
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [Lower("name")]

    def __str__(self):
        return self.name

    @property
    def is_subrecipe(self):
        return self.kind == self.SUBRECIPE

    def bought_unit_cost(self):
        """Cost per unit excl. VAT for bought items (None if no price yet)."""
        if self.pack_price is None or not self.pack_size:
            return None
        return self.pack_price / (1 + self.vat_rate) / self.pack_size


class IngredientPriceChange(models.Model):
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="price_changes")
    changed_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    old_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    new_price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    old_pack_size = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    new_pack_size = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ["-changed_at"]


class Recipe(models.Model):
    number = models.PositiveIntegerField("Recipe no.", unique=True)
    name = models.CharField(max_length=150, unique=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes")
    is_subrecipe = models.BooleanField("Mother recipe", default=False,
                                       help_text="Made here and used inside other recipes (fillings, doughs, sauces…)")
    scaling_weight = models.DecimalField("Scaling weight per unit (kg)", max_digits=10, decimal_places=4,
                                         null=True, blank=True)
    weight_loss = models.DecimalField("Weight loss in baking", max_digits=6, decimal_places=4, default=Decimal("0"),
                                      help_text="0.10 = 10%")
    yield_override = models.PositiveIntegerField("Batch yield (type it)", null=True, blank=True,
                                                 help_text="Only if the yield is not worked out from the scaling weight")
    bake_temp = models.CharField("Baking temp", max_length=200, blank=True)
    bake_time = models.CharField("Baking time", max_length=200, blank=True)
    method = models.TextField(blank=True, help_text="One step per line")
    allergens = models.TextField("Notes / allergens", blank=True)
    sell_price = models.DecimalField("Selling price incl. VAT ($)", max_digits=10, decimal_places=2,
                                     null=True, blank=True)
    EACH, KG = "each", "kg"
    sold_per = models.CharField("Sold per", max_length=4, choices=[(EACH, "each (per item)"), (KG, "kg (by weight)")],
                                default=EACH, help_text="kg = the price is per kg, and counts, sales and waste are in kg (e.g. 2.5)")
    vat_rate = models.DecimalField("VAT on this product", max_digits=6, decimal_places=4, null=True, blank=True,
                                   help_text="Empty = the normal VAT rate from Settings")
    photo = models.FileField(upload_to="recipes/", blank=True)
    par_day = models.PositiveIntegerField("Model stock – day shift", null=True, blank=True,
                                          help_text="How many you want on the shelf after the day shift")
    par_night = models.PositiveIntegerField("Model stock – night shift", null=True, blank=True,
                                            help_text="How many you want ready after the night shift")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [Lower("name")]

    def __str__(self):
        return self.name

    @property
    def unit(self):
        """'kg' or 'each' – for count sheets, price lists and price cards."""
        return self.sold_per or self.EACH

    @staticmethod
    def guess_sold_per(name):
        return "kg" if re.search(r"p/\s*kg|per\s*kg|/\s*kg\b", name or "", re.I) else "each"


class RecipeLine(models.Model):
    DOUGH, TOPPING, PACKAGING = "dough", "topping", "packaging"
    SECTION_CHOICES = [(DOUGH, "Dough / main"), (TOPPING, "Topping / filling"), (PACKAGING, "Packaging")]
    FIXED, PER_UNIT, PER_KG = "fixed", "per_unit", "per_kg"
    MODE_CHOICES = [(FIXED, "for the whole batch"), (PER_UNIT, "per finished item"), (PER_KG, "per kg of dough")]

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="lines")
    section = models.CharField(max_length=10, choices=SECTION_CHOICES, default=DOUGH)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.PROTECT, related_name="used_in")
    qty = models.DecimalField(max_digits=14, decimal_places=4)
    qty_mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=FIXED)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["recipe", "position", "id"]

    def __str__(self):
        return f"{self.recipe}: {self.ingredient} {self.qty}"
