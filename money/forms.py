import datetime
from decimal import Decimal

from django import forms

from .models import Account, BankCheck, Entry

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
MONEY = {"inputmode": "decimal", "step": "0.01"}


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "kind", "number", "opening_date", "opening_balance", "active", "sort_order"]
        widgets = {"opening_date": DATE, "opening_balance": forms.NumberInput(attrs=MONEY)}


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ["date", "kind", "account", "to_account", "amount", "description", "ref"]
        widgets = {"date": DATE, "amount": forms.NumberInput(attrs=MONEY)}
        labels = {"account": "Account"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        qs = Account.objects.filter(active=True)
        if self.instance.pk:
            qs = Account.objects.filter(pk__in=[*qs.values_list("pk", flat=True), self.instance.account_id, self.instance.to_account_id or 0])
        self.fields["account"].queryset = qs
        self.fields["to_account"].queryset = qs
        self.fields["to_account"].required = False
        if not self.instance.pk:
            self.fields["date"].initial = datetime.date.today()

    def clean_amount(self):
        v = self.cleaned_data["amount"]
        if v is None or v <= 0:
            raise forms.ValidationError("Type the amount (more than 0).")
        return v

    def clean(self):
        cd = super().clean()
        if cd.get("kind") == Entry.TRANSFER:
            if not cd.get("to_account"):
                self.add_error("to_account", "Choose the account the money goes to.")
            elif cd.get("to_account") == cd.get("account"):
                self.add_error("to_account", "Choose a different account.")
        else:
            cd["to_account"] = None
        acc, d = cd.get("account"), cd.get("date")
        if acc and d and d < acc.opening_date:
            self.add_error("date", f"{acc} starts on {acc.opening_date:%d %b %Y} – the date can't be before that.")
        return cd


class BankCheckForm(forms.ModelForm):
    class Meta:
        model = BankCheck
        fields = ["date", "statement_balance", "notes"]
        widgets = {"date": DATE, "statement_balance": forms.NumberInput(attrs=MONEY), "notes": forms.Textarea(attrs={"rows": 3})}
