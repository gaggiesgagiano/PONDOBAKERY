import datetime
from decimal import Decimal

from django import forms
from django.forms import modelformset_factory

from .models import CHECKLIST, Advance, Employee, LeaveRecord, PayeBand, PayrollSettings, PayRun, StaffPaper

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
MONEY = {"step": "any", "min": "0", "inputmode": "decimal"}  # arrows go up by $1, cents can still be typed
NUM = {"step": "any", "min": "0", "inputmode": "decimal"}


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["code", "first_name", "middle_name", "last_name", "known_as", "id_number", "date_of_birth", "gender", "job_title", "department",
                  "phone", "address", "next_of_kin", "start_date", "end_date", "active",
                  "pay_type", "rate", "transport_allowance", "other_allowance", "pays_nssa", "pays_paye", "nssa_no",
                  "tax_no", "paid_by", "bank_details", "leave_days", "notes"]
        widgets = {"date_of_birth": DATE, "start_date": DATE, "end_date": DATE,
                   "notes": forms.Textarea(attrs={"rows": 3}),
                   **{f: forms.NumberInput(attrs=MONEY) for f in ("rate", "transport_allowance", "other_allowance")}}

    def __init__(self, *a, **kw):
        from .numbers import next_number

        super().__init__(*a, **kw)
        if not self.instance.pk:
            nxt = next_number()
            self.fields["code"].widget.attrs["placeholder"] = f"{nxt} – given when you save"
            self.fields["code"].help_text = ("Leave it empty: the program gives the next number for the year they "
                                             "started. Use the same number on the fingerprint machine.")
        else:
            self.fields["code"].help_text = ("Each person has their own number. It stays theirs, also after they leave. "
                                             "Use the same number on the fingerprint machine.")
        self.fields["first_name"].required = True
        self.fields["first_name"].error_messages["required"] = "Type the first name (as on the ID)."
        self.fields["first_name"].help_text = "As on the national ID."
        self.fields["rate"].widget.attrs["min"] = "1"
        self.fields["rate"].error_messages["required"] = "Type the salary or rate – at least $1."

    def clean_rate(self):
        r = self.cleaned_data.get("rate")
        if r is None or r < 1:
            raise forms.ValidationError("Type the salary or rate – at least $1.")
        return r

    def clean_code(self):
        from .numbers import taken_by

        code = " ".join((self.cleaned_data.get("code") or "").split())
        other = taken_by(code, self.instance.pk)
        if other:
            raise forms.ValidationError(f"{code} is already {other.name}'s number.")
        return code

    def clean(self):
        cd = super().clean()
        if cd.get("end_date") and cd.get("start_date") and cd["end_date"] < cd["start_date"]:
            self.add_error("end_date", "The leaving date is before the start date.")
        if cd.get("end_date") and cd.get("active"):
            cd["active"] = False  # someone with a leaving date has left
        return cd


class AdvanceForm(forms.ModelForm):
    class Meta:
        model = Advance
        fields = ["date", "amount", "reason"]
        widgets = {"date": DATE, "amount": forms.NumberInput(attrs={**MONEY, "min": "1"})}

    def clean_amount(self):
        a = self.cleaned_data["amount"]
        if a < 1:
            raise forms.ValidationError("An advance is at least $1.")
        return a


def working_days(start, end):
    """Monday to Saturday (bakery week) between two dates, both included."""
    n, d = 0, start
    while d <= end:
        if d.weekday() < 6:
            n += 1
        d += datetime.timedelta(days=1)
    return Decimal(n)


class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveRecord
        fields = ["kind", "start", "end", "days", "notes"]
        widgets = {"start": DATE, "end": DATE, "days": forms.NumberInput(attrs=NUM)}
        help_texts = {"days": "Leave empty to count Monday to Saturday"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["days"].required = False

    def clean(self):
        cd = super().clean()
        s, e = cd.get("start"), cd.get("end")
        if s and e and e < s:
            self.add_error("end", "The last day is before the first day.")
        elif s and e and cd.get("days") in (None, ""):
            cd["days"] = working_days(s, e)
        return cd


class NewPayRunForm(forms.Form):
    month = forms.CharField(label="Month", widget=forms.TextInput(attrs={"type": "month"}))
    pay_date = forms.DateField(widget=DATE)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        today = datetime.date.today()
        self.fields["month"].initial = f"{today:%Y-%m}"
        last = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        self.fields["pay_date"].initial = last

    def clean_month(self):
        try:
            d = datetime.date.fromisoformat(self.cleaned_data["month"].strip() + "-01")
        except ValueError:
            raise forms.ValidationError("Pick a month.")
        if PayRun.objects.filter(period=d).exists():
            raise forms.ValidationError("There is already a pay run for that month – open it from the list.")
        return d


def _dec(**kw):
    return forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, **kw)


class PayLineForm(forms.Form):
    """One worker's row on the pay run screen."""

    days = _dec(widget=forms.NumberInput(attrs=NUM))
    hours = _dec(widget=forms.NumberInput(attrs=NUM))
    unpaid_days = _dec(widget=forms.NumberInput(attrs=NUM))
    overtime_hours = _dec(widget=forms.NumberInput(attrs=NUM))
    holiday_hours = _dec(widget=forms.NumberInput(attrs=NUM))
    allowances = _dec(widget=forms.NumberInput(attrs=MONEY))
    bonus = _dec(widget=forms.NumberInput(attrs=MONEY))
    other_earnings = _dec(widget=forms.NumberInput(attrs=MONEY))
    advances = _dec(widget=forms.NumberInput(attrs=MONEY))
    other_deductions = _dec(widget=forms.NumberInput(attrs=MONEY))
    deduction_note = forms.CharField(max_length=100, required=False)
    remove = forms.BooleanField(required=False)

    def __init__(self, *a, line=None, **kw):
        self.line = line
        super().__init__(*a, **kw)

    def clean(self):
        cd = super().clean()
        if cd.get("remove") or self.line is None:
            return cd
        if self.line.pay_type == "daily" and cd.get("days") is None:
            raise forms.ValidationError(f"Type the days {self.line.employee.first_name} worked.")
        if self.line.pay_type == "hourly" and cd.get("hours") is None:
            raise forms.ValidationError(f"Type the hours {self.line.employee.first_name} worked.")
        return cd


class PercentField(forms.DecimalField):
    def __init__(self, **kw):
        super().__init__(max_digits=7, decimal_places=3, min_value=0, max_value=100, **kw)


class PayrollSettingsForm(forms.ModelForm):
    nssa_pct = PercentField(label="NSSA – worker pays %")
    nssa_er_pct = PercentField(label="NSSA – business pays %")
    aids_pct = PercentField(label="AIDS levy % of PAYE")
    zimdef_pct = PercentField(label="ZIMDEF – business pays %")
    PCT = {"nssa_pct": "nssa_rate", "nssa_er_pct": "nssa_employer_rate", "aids_pct": "aids_levy",
           "zimdef_pct": "zimdef_rate"}

    class Meta:
        model = PayrollSettings
        fields = ["nssa_ceiling", "normal_days", "normal_hours", "day_hours", "overtime_rate", "holiday_rate",
                  "tax_table_note"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f, attr in self.PCT.items():
            self.fields[f].initial = (getattr(self.instance, attr) * 100).normalize()

    def save(self, commit=True):
        i = super().save(commit=False)
        for f, attr in self.PCT.items():
            setattr(i, attr, self.cleaned_data[f] / 100)
        if commit:
            i.save()
        return i


class PayeBandForm(forms.ModelForm):
    rate_pct = forms.DecimalField(label="Rate %", max_digits=6, decimal_places=2, min_value=0, max_value=100,
                                  required=False)

    class Meta:
        model = PayeBand
        fields = ["up_to", "deduct"]
        widgets = {"up_to": forms.NumberInput(attrs=MONEY), "deduct": forms.NumberInput(attrs=MONEY)}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["deduct"].required = False
        if self.instance.pk:
            self.fields["rate_pct"].initial = (self.instance.rate * 100).normalize()

    def has_changed(self):
        if not self.instance.pk and self.is_bound:
            vals = [self.data.get(self.add_prefix(k), "").strip() for k in ("up_to", "rate_pct", "deduct")]
            if not vals[0] and not vals[1] and vals[2] in ("", "0", "0.00"):
                return False  # a blank new row
        return super().has_changed()

    def clean_deduct(self):
        return self.cleaned_data.get("deduct") or Decimal("0")

    def clean(self):
        cd = super().clean()
        if self.has_changed() and not cd.get("DELETE") and cd.get("rate_pct") is None:
            self.add_error("rate_pct", "Type the rate.")
        return cd

    def save(self, commit=True):
        i = super().save(commit=False)
        i.rate = self.cleaned_data["rate_pct"] / 100
        if commit:
            i.save()
        return i


PayeBandFormSet = modelformset_factory(PayeBand, form=PayeBandForm, extra=1, can_delete=True)


# ======================================================================= the staff file
class PaperForm(forms.ModelForm):
    class Meta:
        model = StaffPaper
        fields = ["kind", "title", "expires", "hard_copy", "notes"]
        widgets = {"expires": DATE}


class StaffFileSettingsForm(forms.ModelForm):
    needs = forms.MultipleChoiceField(label="Every staff file should have", required=False,
                                      choices=[(k, label) for k, label, _ in CHECKLIST],
                                      widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = PayrollSettings
        fields = ["staff_no_style", "staff_no_prefix", "staff_no_digits"]
        widgets = {"staff_no_style": forms.RadioSelect, "staff_no_prefix": forms.TextInput(attrs={"style": "max-width:140px"}),
                   "staff_no_digits": forms.NumberInput(attrs={"min": 1, "max": 6, "style": "max-width:100px"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["needs"].initial = [k for k in self.instance.file_needs.split(",") if k]

    def clean_staff_no_prefix(self):
        p = (self.cleaned_data.get("staff_no_prefix") or "").strip()
        if p and p[-1].isdigit():
            raise forms.ValidationError("Don't end with a number – use a letter or a dash, like PB-.")
        return p.upper()

    def clean(self):
        cd = super().clean()
        if cd.get("staff_no_style") == PayrollSettings.LETTERS and not cd.get("staff_no_prefix"):
            self.add_error("staff_no_prefix", "Type the letters, e.g. PB-")
        return cd

    def clean_staff_no_digits(self):
        d = self.cleaned_data.get("staff_no_digits") or 3
        if not 1 <= d <= 6:
            raise forms.ValidationError("Use 1 to 6 digits.")
        return d

    def save(self, commit=True):
        self.instance.file_needs = ",".join(self.cleaned_data["needs"])
        return super().save(commit)
