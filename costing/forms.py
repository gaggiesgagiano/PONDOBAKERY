from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory

from core.fields import TidyDecimalField

from .models import Category, Ingredient, Recipe, RecipeLine, Supplier

PCT = {"max_digits": 7, "decimal_places": 3, "required": False}


class RecipeForm(forms.ModelForm):
    loss_percent = TidyDecimalField(label="Weight loss in baking %", min_value=0, max_value=95, **PCT,
                                      help_text="e.g. 12 for 12%. Leave empty for none.")
    vat_percent = TidyDecimalField(label="VAT on this product %", min_value=0, max_value=100, **PCT,
                                     help_text="Leave empty to use the normal rate. Type 0 for zero-rated (e.g. bread).")

    class Meta:
        model = Recipe
        fields = ["name", "number", "category", "is_subrecipe", "scaling_weight", "yield_override",
                  "bake_temp", "bake_time", "method", "allergens", "sell_price", "sold_per", "photo", "active",
                  "par_day", "par_night"]
        widgets = {
            "method": forms.Textarea(attrs={"rows": 8}),
            "allergens": forms.Textarea(attrs={"rows": 3}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }
        labels = {"photo": "Product photo"}

    def clean_sold_per(self):
        v = self.cleaned_data.get("sold_per")
        if v:
            return v
        if self.instance.pk:
            return self.instance.sold_per
        return Recipe.guess_sold_per(self.data.get("name", ""))

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        i = self.instance
        if i.scaling_weight is not None:
            self.initial["scaling_weight"] = format(i.scaling_weight.normalize(), "f")
        if i.pk:
            self.fields["loss_percent"].initial = (i.weight_loss or 0) * 100 or None
            self.fields["vat_percent"].initial = None if i.vat_rate is None else i.vat_rate * 100
        else:
            from .numbers import suggestions

            free = suggestions(1)  # the first free number (a gap first, otherwise the next one)
            self.fields["number"].initial = free[0] if free else 201001
        self.fields["category"].queryset = Category.objects.all()
        if "sold_per" in self.fields:
            self.fields["sold_per"].required = False

    def clean_name(self):
        n = " ".join(self.cleaned_data["name"].split())
        qs = Recipe.objects.filter(name__iexact=n).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Another recipe already has this name.")
        return n

    def save(self, commit=True):
        r = super().save(commit=False)
        lp = self.cleaned_data.get("loss_percent")
        r.weight_loss = (lp / 100) if lp else Decimal("0")
        if "vat_percent" in self.fields:
            vp = self.cleaned_data.get("vat_percent")
            r.vat_rate = None if vp is None else vp / 100
        if commit:
            r.save()
        return r


class LineForm(forms.Form):
    section = forms.ChoiceField(choices=RecipeLine.SECTION_CHOICES)
    ingredient = forms.CharField(max_length=150, required=False,
                                 widget=forms.TextInput(attrs={"list": "ingredient-names", "autocomplete": "off"}))
    qty = TidyDecimalField(max_digits=14, decimal_places=4, required=False, min_value=0)
    qty_mode = forms.ChoiceField(choices=RecipeLine.MODE_CHOICES, initial=RecipeLine.FIXED)

    def clean(self):
        cd = super().clean()
        name = " ".join((cd.get("ingredient") or "").split())
        if not name and cd.get("qty") in (None, ""):
            cd["empty"] = True
            return cd
        if not name:
            raise forms.ValidationError("Choose an ingredient for this line.")
        ing = Ingredient.objects.filter(name__iexact=name).first()
        if not ing:
            raise forms.ValidationError(f"'{name}' is not on the ingredient list. Add it under Ingredients first.")
        if cd.get("qty") in (None, ""):
            raise forms.ValidationError(f"Type a quantity for {ing.name}.")
        cd["ingredient_obj"] = ing
        return cd


class BaseLineFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        rec = getattr(self, "recipe", None)
        for f in self.forms:
            ing = f.cleaned_data.get("ingredient_obj")
            if rec and ing and ing.recipe_id and ing.recipe_id == rec.pk:
                raise forms.ValidationError(f"A recipe cannot use itself ({ing.name}).")


LineFormSet = formset_factory(LineForm, formset=BaseLineFormSet, extra=3, can_delete=True)


class IngredientForm(forms.ModelForm):
    vat_percent = TidyDecimalField(label="VAT included in pack price %", min_value=0, max_value=100, **PCT,
                                     help_text="0 or empty if you cannot claim VAT back on it")

    class Meta:
        model = Ingredient
        fields = ["name", "kind", "supplier", "code", "unit", "pack_size", "pack_price", "recipe", "reorder_level",
                  "stock_par", "active", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ("pack_size", "pack_price"):
            v = getattr(self.instance, f)
            if v is not None:
                self.initial[f] = format(v.normalize(), "f")
        self.fields["vat_percent"].initial = (self.instance.vat_rate or 0) * 100 or None
        self.fields["supplier"].queryset = Supplier.objects.filter(active=True)
        # usually a sub-recipe (dough, filling), but a product can be used in another recipe too
        # (White Bread 600g in Bread Crumbs) – keep the link it already has
        from django.db.models import Q

        self.fields["recipe"].queryset = Recipe.objects.filter(
            Q(is_subrecipe=True) | Q(pk=self.instance.recipe_id or 0)).order_by("-is_subrecipe", "name")
        self.fields["recipe"].required = False

    def clean_name(self):
        n = " ".join(self.cleaned_data["name"].split())
        if Ingredient.objects.filter(name__iexact=n).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another ingredient already has this name.")
        return n

    def clean(self):
        cd = super().clean()
        if cd.get("kind") == Ingredient.SUBRECIPE:
            if not cd.get("recipe"):
                self.add_error("recipe", "Choose the mother recipe that makes this.")
        else:
            cd["recipe"] = None
            if not cd.get("pack_size"):
                self.add_error("pack_size", "Type the pack size (e.g. 25 for a 25 kg bag).")
        return cd

    def save(self, commit=True):
        i = super().save(commit=False)
        vp = self.cleaned_data.get("vat_percent")
        i.vat_rate = (vp / 100) if vp else Decimal("0")
        if i.kind == Ingredient.SUBRECIPE:
            i.pack_price, i.pack_size = None, Decimal("1")
        if commit:
            i.save()
        return i


class NameForm(forms.Form):
    name = forms.CharField(max_length=80)
