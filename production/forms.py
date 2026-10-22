import datetime

from django import forms
from django.forms import formset_factory

from costing.models import Recipe

from .models import SHIFTS, WASTE_REASONS, ProductionPlan, WasteLog


def find_recipe(name):
    name = " ".join((name or "").split())
    return Recipe.objects.filter(name__iexact=name, active=True).first() if name else None


class NewPlanForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), initial=datetime.date.today)
    shift = forms.ChoiceField(choices=SHIFTS)
    start = forms.ChoiceField(label="Start with", choices=[
        ("model", "All products that have a model stock for this shift"),
        ("copy", "A copy of the last plan for this shift"),
        ("empty", "An empty plan"),
    ])

    def clean(self):
        cd = super().clean()
        if cd.get("date") and cd.get("shift") and ProductionPlan.objects.filter(date=cd["date"], shift=cd["shift"]).exists():
            raise forms.ValidationError("There is already a plan for that date and shift – open it from the list.")
        return cd


class PlanHeaderForm(forms.ModelForm):
    class Meta:
        model = ProductionPlan
        fields = ["supervisor", "status", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class PlanLineForm(forms.Form):
    product = forms.CharField(max_length=150, required=False,
                              widget=forms.TextInput(attrs={"list": "product-names", "autocomplete": "off"}))
    model_stock = forms.IntegerField(min_value=0, required=False)
    on_hand = forms.IntegerField(min_value=0, required=False)
    expired = forms.IntegerField(min_value=0, required=False)
    actual = forms.IntegerField(min_value=0, required=False)

    def clean(self):
        cd = super().clean()
        if not (cd.get("product") or "").strip():
            cd["empty"] = True
            return cd
        r = find_recipe(cd["product"])
        if not r:
            raise forms.ValidationError(f"'{cd['product']}' is not a recipe. Pick it from the list.")
        cd["recipe"] = r
        return cd


PlanLineFormSet = formset_factory(PlanLineForm, extra=3, can_delete=True)


class NewWasteForm(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"), initial=datetime.date.today)
    shift = forms.ChoiceField(choices=SHIFTS)

    def clean(self):
        cd = super().clean()
        if cd.get("date") and cd.get("shift") and WasteLog.objects.filter(date=cd["date"], shift=cd["shift"]).exists():
            raise forms.ValidationError("There is already a waste log for that date and shift – open it from the list.")
        return cd


class WasteHeaderForm(forms.ModelForm):
    class Meta:
        model = WasteLog
        fields = ["notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class WasteLineForm(forms.Form):
    product = forms.CharField(max_length=150, required=False,
                              widget=forms.TextInput(attrs={"list": "product-names", "autocomplete": "off"}))
    qty = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    reason = forms.ChoiceField(choices=[(r, r) for r in WASTE_REASONS])
    notes = forms.CharField(max_length=200, required=False)

    def clean(self):
        cd = super().clean()
        if not (cd.get("product") or "").strip():
            cd["empty"] = True
            return cd
        r = find_recipe(cd["product"])
        if not r:
            raise forms.ValidationError(f"'{cd['product']}' is not a product. Pick it from the list.")
        if not cd.get("qty"):
            raise forms.ValidationError(f"Type how many {r.name} were wasted.")
        cd["recipe"] = r
        return cd


WasteLineFormSet = formset_factory(WasteLineForm, extra=5, can_delete=True)
