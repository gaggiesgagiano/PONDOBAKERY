import datetime

from django import forms
from django.forms import formset_factory

from costing.models import Ingredient, Supplier

from .models import GRV, PurchaseOrder, StockCount


def find_ingredient(name):
    name = " ".join((name or "").split())
    return Ingredient.objects.filter(name__iexact=name).exclude(kind=Ingredient.SUBRECIPE).first() if name else None


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "company_name", "contact", "phone", "email", "address", "account_no", "terms_days", "notes", "active"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class OrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ["supplier", "date", "delivery_date", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), "delivery_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"delivery_date": "Expected on", "notes": "Notes for the supplier"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["supplier"].queryset = Supplier.objects.filter(active=True)
        if not self.instance.pk:
            self.initial["date"] = self.initial.get("date") or datetime.date.today()


class ItemLineForm(forms.Form):
    item = forms.CharField(max_length=150, required=False,
                           widget=forms.TextInput(attrs={"list": "item-names", "autocomplete": "off"}))
    packs = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    pack_price = forms.DecimalField(max_digits=12, decimal_places=4, min_value=0, required=False)

    def clean(self):
        cd = super().clean()
        if not (cd.get("item") or "").strip():
            cd["empty"] = True
            return cd
        i = find_ingredient(cd["item"])
        if not i:
            raise forms.ValidationError(f"'{cd['item']}' is not on the ingredient list.")
        if cd.get("packs") in (None, ""):
            raise forms.ValidationError(f"Type how many packs of {i.name}.")
        cd["ingredient"] = i
        if cd.get("pack_price") in (None, ""):
            cd["pack_price"] = i.pack_price or 0
        return cd


class GRVLineForm(ItemLineForm):
    packs_ordered = forms.DecimalField(max_digits=10, decimal_places=2, required=False,
                                       widget=forms.NumberInput(attrs={"readonly": "readonly", "tabindex": "-1"}))


OrderLineFormSet = formset_factory(ItemLineForm, extra=3, can_delete=True)
GRVLineFormSet = formset_factory(GRVLineForm, extra=3, can_delete=True)


class GRVForm(forms.ModelForm):
    update_prices = forms.BooleanField(label="Update the ingredient prices to these invoice prices", required=False,
                                       initial=True)

    class Meta:
        model = GRV
        fields = ["supplier", "date", "invoice_no", "invoice_total", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["supplier"].queryset = Supplier.objects.filter(active=True)
        if not self.instance.pk:
            self.initial["date"] = self.initial.get("date") or datetime.date.today()


class CountHeaderForm(forms.ModelForm):
    class Meta:
        model = StockCount
        fields = ["date", "counted_by", "checked_by", "notes"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), "notes": forms.Textarea(attrs={"rows": 2})}
