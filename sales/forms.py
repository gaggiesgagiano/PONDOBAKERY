from decimal import Decimal
import datetime

from django import forms
from django.forms import formset_factory

from production.forms import find_recipe

from .models import CashUp, DaySales, Expense, ExpenseCategory, PaymentMethod

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
MONEY = {"step": "any", "min": "0", "inputmode": "decimal"}  # arrows go up by $1, cents can still be typed


TILLS = ["Till 1", "Till 2"]  # the bakery's tills – add a name here if a till is ever added


def cashier_field(current=""):
    """Pick the cashier from the staff list, so every cash-up of a person carries exactly the same name
    (the over & short report adds them up by name). Without any staff yet: a normal typing box."""
    from staff.models import Employee
    names = sorted({e.name for e in Employee.objects.filter(active=True) if not e.is_open and e.name})
    if not names:
        return forms.CharField(label="Cashier", max_length=80, required=False, initial=current)
    if current and current not in names:
        names.append(current)  # an older cash-up with a name typed by hand
    return forms.ChoiceField(label="Cashier", choices=[("", "– pick the cashier –")] + [(n, n) for n in names],
                             initial=current, help_text="The person who worked this till")


class NewCashUpForm(forms.Form):
    date = forms.DateField(widget=DATE, initial=datetime.date.today)
    till = forms.ChoiceField(label="Till", choices=[(t, t) for t in TILLS], initial=TILLS[0],
                             help_text="Busy day with both tills open? Cash up each till on its own.")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["cashier"] = cashier_field()
        if isinstance(self.fields["cashier"], forms.ChoiceField):
            self.fields["cashier"].required = True

    def clean(self):
        cd = super().clean()
        if cd.get("date") and cd.get("till") and CashUp.objects.filter(date=cd["date"], till__iexact=cd["till"].strip()).exists():
            raise forms.ValidationError("There is already a cash-up for that till on that day – open it from the list.")
        return cd


class CashUpHeaderForm(forms.ModelForm):
    class Meta:
        model = CashUp
        fields = ["cashier", "opening_float", "drops", "cash_counted", "zig_counted", "zig_rate", "float_left", "banked", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2}),
                   "zig_rate": forms.NumberInput(attrs={"step": "any", "min": "0", "inputmode": "decimal"}),
                   **{f: forms.NumberInput(attrs=MONEY) for f in ("opening_float", "drops", "cash_counted", "zig_counted", "float_left", "banked")}}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["cashier"] = cashier_field(self.instance.cashier if self.instance else "")
        self.fields["drops"].required = False

    def clean_drops(self):
        return self.cleaned_data.get("drops") or 0

    def clean(self):
        cd = super().clean()
        if cd.get("zig_counted") and not cd.get("zig_rate"):
            self.add_error("zig_rate", "Type the ZiG rate of the day to change the ZiG into US$.")
        return cd


class TakingsForm(forms.Form):
    """One 'till says' (and, for non-cash, 'really received') box per payment type."""

    def __init__(self, *a, methods=(), **kw):
        super().__init__(*a, **kw)
        self.methods = list(methods)
        for m in self.methods:
            self.fields[f"till_{m.pk}"] = forms.DecimalField(label=f"{m.name} – till says", required=False,
                                                             max_digits=12, decimal_places=2, min_value=0,
                                                             widget=forms.NumberInput(attrs=MONEY))
            if not m.is_cash:
                self.fields[f"actual_{m.pk}"] = forms.DecimalField(
                    label=f"{m.name} – really received", required=False, max_digits=12, decimal_places=2, min_value=0,
                    widget=forms.NumberInput(attrs=MONEY))

    def rows(self):
        for m in self.methods:
            yield m, self[f"till_{m.pk}"], (None if m.is_cash else self[f"actual_{m.pk}"])


class PayoutForm(forms.Form):
    category = forms.ModelChoiceField(queryset=ExpenseCategory.objects.filter(active=True), required=False,
                                      empty_label="– pick –")
    payee = forms.CharField(max_length=100, required=False)
    description = forms.CharField(max_length=200, required=False)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False,
                                widget=forms.NumberInput(attrs=MONEY))
    receipt_no = forms.CharField(max_length=60, required=False)

    def clean(self):
        cd = super().clean()
        if not cd.get("amount") and not cd.get("category") and not (cd.get("description") or "").strip():
            cd["empty"] = True
            return cd
        if not cd.get("amount"):
            raise forms.ValidationError("Type how much was paid out.")
        if not cd.get("category"):
            raise forms.ValidationError("Pick what the money was for.")
        return cd


PayoutFormSet = formset_factory(PayoutForm, extra=2, can_delete=True)


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "amount", "vat", "paid_from", "account", "payee", "description", "receipt_no"]
        widgets = {"date": DATE, "amount": forms.NumberInput(attrs=MONEY), "vat": forms.NumberInput(attrs=MONEY)}

    def clean_vat(self):
        return self.cleaned_data.get("vat") or Decimal("0")

    def clean(self):
        cd = super().clean()
        if cd.get("vat") and cd.get("amount") is not None and cd["vat"] > cd["amount"]:
            self.add_error("vat", "The VAT can't be more than the amount.")
        return cd

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        qs = ExpenseCategory.objects.filter(active=True)
        if self.instance.pk and self.instance.category_id:
            qs = ExpenseCategory.objects.filter(active=True) | ExpenseCategory.objects.filter(pk=self.instance.category_id)
        self.fields["category"].queryset = qs.distinct()
        self.fields["category"].empty_label = "– pick –"
        self.fields["vat"].required = False
        from money.models import Account
        self.fields["account"].queryset = Account.objects.filter(active=True).exclude(kind=Account.SAFE)
        self.fields["account"].required = False
        self.fields["account"].empty_label = "– the bank –"
        if not self.instance.pk:
            self.fields["date"].initial = datetime.date.today


class NewDaySalesForm(forms.Form):
    date = forms.DateField(widget=DATE, initial=datetime.date.today)
    start = forms.ChoiceField(label="Start with", choices=[
        ("empty", "An empty list – I'll type the products"),
        ("copy", "The products from the last day (quantities empty)"),
        ("all", "Every product that has a selling price"),
    ])

    def clean_date(self):
        d = self.cleaned_data["date"]
        if DaySales.objects.filter(date=d).exists():
            raise forms.ValidationError("Product sales for that day already exist – open them from the list.")
        return d


class SaleLineForm(forms.Form):
    product = forms.CharField(max_length=150, required=False,
                              widget=forms.TextInput(attrs={"list": "product-names", "autocomplete": "off"}))
    qty = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False,
                             widget=forms.NumberInput(attrs={"step": "any", "min": "0", "inputmode": "decimal"}))
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False,
                               widget=forms.NumberInput(attrs=MONEY),
                               help_text="Empty = today's selling price")

    def clean(self):
        cd = super().clean()
        if not (cd.get("product") or "").strip():
            cd["empty"] = True
            return cd
        r = find_recipe(cd["product"])
        if not r:
            raise forms.ValidationError(f"'{cd['product']}' is not a product. Pick it from the list.")
        if not cd.get("qty"):
            cd["empty"] = True  # a product with no quantity is simply skipped
            return cd
        cd["recipe"] = r
        return cd


SaleLineFormSet = formset_factory(SaleLineForm, extra=5, can_delete=True)


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["name", "is_cash", "sort_order", "active"]


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "sort_order", "active"]
