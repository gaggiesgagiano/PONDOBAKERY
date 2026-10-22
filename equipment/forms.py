from django import forms
from django.forms import modelformset_factory

from .models import EquipmentCategory, Item, Location

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["asset_no", "description", "category", "location", "serial", "supplier", "purchase_date", "unit_cost",
                  "qty", "life_override", "scrap_value", "disposed_on", "disposed_note", "notes"]
        widgets = {"purchase_date": DATE, "disposed_on": DATE, "notes": forms.Textarea(attrs={"rows": 2}),
                   "unit_cost": forms.NumberInput(attrs={"step": "any", "min": "0"})}

    def clean(self):
        cd = super().clean()
        if cd.get("disposed_on") and cd.get("purchase_date") and cd["disposed_on"] < cd["purchase_date"]:
            self.add_error("disposed_on", "This is before the purchase date.")
        return cd


CategoryFormSet = modelformset_factory(EquipmentCategory, fields=["name", "life_years"], extra=2, can_delete=False)
LocationFormSet = modelformset_factory(Location, fields=["name"], extra=2, can_delete=False)
