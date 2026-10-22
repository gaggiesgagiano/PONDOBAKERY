from decimal import Decimal
from .access import PRESETS
from django import forms
from django.contrib.auth.models import User

from .fields import TidyDecimalField
from .models import CompanySettings, Overhead, Shop


class ShopForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ["name", "address_line1", "address_line2", "phone", "email", "tin", "vat_no", "payment_details"]
        widgets = {"payment_details": forms.Textarea(attrs={"rows": 3})}


class CompanySettingsForm(forms.ModelForm):
    vat_percent = TidyDecimalField(label="VAT %", max_digits=6, decimal_places=2)
    target_percent = TidyDecimalField(label="Target gross profit %", max_digits=6, decimal_places=2)
    low_percent = TidyDecimalField(label="Show GP in red below %", max_digits=6, decimal_places=2)

    zwg_rate = TidyDecimalField(label="ZWG per US$1", max_digits=10, decimal_places=4, required=False,
                                min_value=Decimal("0.0001"),
                                help_text="The till changes ZWG payments to US$ at this rate – every sale from the moment you save.")

    class Meta:
        model = CompanySettings
        fields = ["company_name", "zwg_rate"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        i = self.instance
        self.fields["vat_percent"].initial = i.vat_rate * 100
        self.fields["target_percent"].initial = i.target_gp * 100
        self.fields["low_percent"].initial = i.gp_low * 100

    def save(self, commit=True):
        i = super().save(commit=False)
        i.vat_rate = self.cleaned_data["vat_percent"] / 100
        i.target_gp = self.cleaned_data["target_percent"] / 100
        i.gp_low = self.cleaned_data["low_percent"] / 100
        if commit:
            i.save()
        return i


class NewUserForm(forms.Form):
    username = forms.CharField(max_length=40, help_text="Used to log in, e.g. 'tendai'")
    first_name = forms.CharField(max_length=60, required=False, label="Name")
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, help_text="At least 8 characters")
    role = forms.ChoiceField(label="Starting rights", choices=[(k, p["label"]) for k, p in PRESETS.items()],
                             help_text="You can fine-tune every right after adding the person")

    def clean_username(self):
        u = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError("That username is already used.")
        return u


class TargetsForm(forms.ModelForm):
    waste_percent = TidyDecimalField(label="Waste target – maximum % of sales", max_digits=5, decimal_places=2,
                                       min_value=0, max_value=100)
    gp_percent = TidyDecimalField(label="GP % to use for break-even (optional)", max_digits=5, decimal_places=2,
                                    min_value=1, max_value=99, required=False,
                                    help_text="Leave empty to use the average GP of your products")

    class Meta:
        model = CompanySettings
        fields = ["profit_target", "trading_days"]
        widgets = {"profit_target": forms.NumberInput(attrs={"step": "1", "min": "0"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        i = self.instance
        self.fields["waste_percent"].initial = (i.waste_target * 100).normalize()
        self.fields["gp_percent"].initial = None if i.gp_override is None else (i.gp_override * 100).normalize()
        self.fields["trading_days"].widget.attrs.update({"min": 1, "max": 7})

    def clean_trading_days(self):
        v = self.cleaned_data["trading_days"]
        if not 1 <= v <= 7:
            raise forms.ValidationError("Between 1 and 7 days.")
        return v

    def save(self, commit=True):
        i = super().save(commit=False)
        i.waste_target = self.cleaned_data["waste_percent"] / 100
        g = self.cleaned_data.get("gp_percent")
        i.gp_override = None if g is None else g / 100
        if commit:
            i.save()
        return i


OverheadFormSet = forms.modelformset_factory(Overhead, fields=["name", "monthly_cost"], extra=3, can_delete=True,
                                             widgets={"monthly_cost": forms.NumberInput(attrs={"step": "any", "min": "0"})})
