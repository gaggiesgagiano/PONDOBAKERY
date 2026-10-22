import datetime
from decimal import Decimal

from django import forms
from django.forms import formset_factory

from costing.models import Recipe

from .models import Customer, Delivery, Document, Driver

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class DocumentForm(forms.ModelForm):
    save_customer = forms.BooleanField(label="Add to my customers", required=False, initial=True)

    class Meta:
        model = Document
        fields = ["kind", "date", "due", "customer", "name", "company", "address1", "address2", "phone", "email",
                  "vat_no", "your_ref", "prepared_by", "notes"]
        widgets = {"date": DATE, "due": DATE, "notes": forms.Textarea(attrs={"rows": 2})}
        labels = {"customer": "Pick a customer", "name": "Customer name"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["customer"].queryset = Customer.objects.filter(active=True)
        self.fields["customer"].empty_label = "– new customer –"
        self.fields["customer"].required = False
        if self.instance.pk:
            self.fields["kind"].disabled = True  # the number belongs to the type
            self.fields["save_customer"].initial = False


class LineForm(forms.Form):
    product = forms.CharField(max_length=200, required=False,
                              widget=forms.TextInput(attrs={"list": "product-names", "autocomplete": "off"}))
    qty = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False,
                             widget=forms.NumberInput(attrs={"step": "any", "min": "0"}))
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False,
                               widget=forms.NumberInput(attrs={"step": "any", "min": "0"}))
    discount = forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False,
                                  widget=forms.NumberInput(attrs={"step": "any", "min": "0", "max": "100"}))

    def clean(self):
        cd = super().clean()
        text = " ".join((cd.get("product") or "").split())
        if not text:
            cd["empty"] = True
            return cd
        cd["recipe"] = Recipe.objects.filter(name__iexact=text, active=True).first()
        cd["description"] = cd["recipe"].name if cd["recipe"] else text
        if not cd.get("qty"):
            raise forms.ValidationError(f"Type how many of '{text}'.")
        if cd.get("price") is None:
            if cd["recipe"] and cd["recipe"].sell_price is not None:
                cd["price"] = cd["recipe"].sell_price
            else:
                raise forms.ValidationError(f"Type the price of '{text}'.")
        cd["discount"] = (cd.get("discount") or Decimal("0")) / 100
        return cd


LineFormSet = formset_factory(LineForm, extra=5, can_delete=True)


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "company", "address1", "address2", "phone", "email", "vat_no", "tin", "notes", "active"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


class PaidForm(forms.Form):
    paid_on = forms.DateField(label="Paid on", widget=DATE, initial=datetime.date.today)
    paid_how = forms.ChoiceField(label="Paid how", choices=[(x, x) for x in ("Bank transfer", "Cash", "EcoCash",
                                                                              "Swipe / card", "Other")])


# ======================================================================= deliveries
class DeliveryCustomerForm(forms.ModelForm):
    """Who gets the order and where (kept on the delivery's tax invoice)."""

    save_customer = forms.BooleanField(label="Add to my customers", required=False, initial=True)

    class Meta:
        model = Document
        fields = ["customer", "name", "phone", "company", "address1", "address2", "your_ref"]
        labels = {"customer": "Pick a customer", "name": "Customer name", "phone": "Customer cell",
                  "address1": "Deliver to – street & number", "address2": "Suburb / area",
                  "your_ref": "Order no. / WhatsApp ref"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["customer"].queryset = Customer.objects.filter(active=True)
        self.fields["customer"].empty_label = "– new customer –"
        self.fields["customer"].required = False
        self.fields["address1"].required = True
        if self.instance.pk:
            self.fields["save_customer"].initial = False


class DeliveryForm(forms.ModelForm):
    """Deliveries are cash only: the customer pays the driver, the driver keeps the fee and brings back the rest."""

    class Meta:
        model = Delivery
        fields = ["date", "directions", "driver", "driver_name", "driver_phone", "car_reg", "car_make", "car_colour",
                  "fee", "notes"]
        widgets = {"date": DATE, "notes": forms.Textarea(attrs={"rows": 2}),
                   "fee": forms.NumberInput(attrs={"step": "any", "min": "0", "inputmode": "decimal"}),
                   "driver_name": forms.TextInput(attrs={"autocomplete": "off"}),
                   "car_reg": forms.TextInput(attrs={"style": "text-transform:uppercase", "autocomplete": "off"})}
        labels = {"driver": "Pick a driver from the list"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["driver"].queryset = Driver.objects.filter(active=True)
        self.fields["driver"].empty_label = "– a new driver –"
        self.fields["driver"].required = False
        self.fields["fee"].error_messages["required"] = "Type the delivery fee – 0 if there is none."
        self.fields["car_reg"].error_messages["required"] = "Type the car registration before the driver leaves."

    def clean_car_reg(self):
        return " ".join((self.cleaned_data.get("car_reg") or "").upper().split())

    def clean_fee(self):
        f = self.cleaned_data.get("fee")
        if f is None or f < 0:
            raise forms.ValidationError("Type the delivery fee – 0 if there is none.")
        return f


class MoneyBackForm(forms.Form):
    money_back = forms.DecimalField(label="Money the driver brought back ($)", max_digits=12, decimal_places=2,
                                    min_value=0, required=False,
                                    widget=forms.NumberInput(attrs={"step": "any", "min": "0", "inputmode": "decimal"}))
    rung_up = forms.DecimalField(label="Rung up on the till ($)", max_digits=12, decimal_places=2, min_value=0,
                                 widget=forms.NumberInput(attrs={"step": "any", "min": "0", "inputmode": "decimal"}))
    till_ref = forms.CharField(label="Till slip / receipt no.", max_length=40, required=False)
    back_note = forms.CharField(label="Note", max_length=200, required=False)

    def __init__(self, *a, delivery=None, **kw):
        self.delivery = delivery
        super().__init__(*a, **kw)
        if delivery and not delivery.by_driver:  # only old deliveries from before 'cash only'
            del self.fields["money_back"]

    def clean(self):
        cd = super().clean()
        if self.delivery and self.delivery.by_driver and cd.get("money_back") is None:
            self.add_error("money_back", "Count the money from the driver and type it.")
        return cd



class DriverForm(forms.ModelForm):
    class Meta:
        model = Driver
        fields = ["name", "phone", "id_number", "licence_no", "car_reg", "car_make", "car_colour", "issued", "active", "notes"]
        widgets = {"issued": DATE, "notes": forms.Textarea(attrs={"rows": 2}),
                   "car_reg": forms.TextInput(attrs={"style": "text-transform:uppercase", "autocomplete": "off"})}

    def clean_car_reg(self):
        return " ".join((self.cleaned_data.get("car_reg") or "").upper().split())

    def clean_id_number(self):
        return " ".join((self.cleaned_data.get("id_number") or "").upper().split())
