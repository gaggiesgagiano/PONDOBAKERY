"""Staff records, advances, leave and monthly payroll (Zimbabwe, US$).

Pay maths lives in paycalc.py. Every figure on a pay line is stored when it is worked out, so an old
payslip never changes when rates or tax tables change later.
"""
import datetime
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .storage import staff_storage

Z = Decimal("0")


def photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:8] or ".jpg"
    return f"{instance.pk}/photo-{uuid.uuid4().hex[:8]}{ext}"

DEPARTMENTS = [("production", "Production / bakers"), ("shop", "Shop / counter"), ("delivery", "Drivers / delivery"),
               ("cleaning", "Cleaning / general"), ("security", "Security"), ("admin", "Admin / management")]


class PayrollSettings(models.Model):
    """One row. Rates used for every pay run (copied onto each pay line when worked out)."""

    nssa_rate = models.DecimalField("NSSA – employee", max_digits=6, decimal_places=4, default=Decimal("0.045"),
                                    help_text="0.045 = 4.5% taken off the worker's pay")
    nssa_employer_rate = models.DecimalField("NSSA – employer", max_digits=6, decimal_places=4,
                                             default=Decimal("0.045"), help_text="0.045 = 4.5% the business pays on top")
    nssa_ceiling = models.DecimalField("NSSA insurable earnings ceiling ($ / month)", max_digits=10,
                                       decimal_places=2, default=Decimal("700"),
                                       help_text="NSSA is only worked out on pay up to this amount. Check with NSSA when it changes.")
    aids_levy = models.DecimalField("AIDS levy", max_digits=6, decimal_places=4, default=Decimal("0.03"),
                                    help_text="0.03 = 3% of the PAYE")
    zimdef_rate = models.DecimalField("ZIMDEF – employer", max_digits=6, decimal_places=4, default=Decimal("0.01"),
                                      help_text="0.01 = 1% of the total wage bill, paid by the business")
    normal_days = models.DecimalField("Working days in a month", max_digits=5, decimal_places=2, default=Decimal("26"),
                                      help_text="Used to take off unpaid days from a monthly salary")
    normal_hours = models.DecimalField("Working hours in a month", max_digits=6, decimal_places=2,
                                       default=Decimal("208"), help_text="Used to work out the hourly rate for overtime")
    day_hours = models.DecimalField("Hours in a working day", max_digits=4, decimal_places=2, default=Decimal("8"),
                                    help_text="For overtime of day-rate workers")
    overtime_rate = models.DecimalField("Overtime pays", max_digits=4, decimal_places=2, default=Decimal("1.5"),
                                        help_text="1.5 = time and a half")
    holiday_rate = models.DecimalField("Sunday / public holiday pays", max_digits=4, decimal_places=2,
                                       default=Decimal("2"), help_text="2 = double time")
    tax_table_note = models.CharField("Tax table in use", max_length=120, default="ZIMRA USD Jan–Dec 2025 (monthly)")
    YEAR, LETTERS = "year", "prefix"
    staff_no_style = models.CharField("Staff numbers look like", max_length=6, default=YEAR,
                                      choices=[(YEAR, "Year started + number – 26001, 26002 …"),
                                               (LETTERS, "Letters + number – e.g. PB-001")])
    staff_no_prefix = models.CharField("Letters in front", max_length=8, default="", blank=True,
                                       help_text="Only for 'Letters + number', e.g. PB- gives PB-001.")
    staff_no_digits = models.PositiveSmallIntegerField("Digits after the year / letters", default=3,
                                                       help_text="3 gives 001 to 999 (26001 – 26999)")
    file_needs = models.CharField("Every staff file should have", max_length=200,
                                  default="id,contract,cv,fingerprints,medical")

    class Meta:
        verbose_name_plural = "payroll settings"

    def __str__(self):
        return "Payroll settings"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    @property
    def needs(self):
        return [k for k in self.file_needs.split(",") if k]


class PayeBand(models.Model):
    """One row of the monthly PAYE table: tax = taxable pay × rate − deduct."""

    up_to = models.DecimalField("Pay up to ($ / month)", max_digits=12, decimal_places=2, null=True, blank=True,
                                help_text="Empty for the top band (and above)")
    rate = models.DecimalField(max_digits=6, decimal_places=4, help_text="0.25 = 25%")
    deduct = models.DecimalField("Deduct ($)", max_digits=12, decimal_places=2, default=Z)

    class Meta:
        ordering = [models.F("up_to").asc(nulls_last=True)]

    def __str__(self):
        return f"up to {self.up_to or 'and above'}: {self.rate}"


class Employee(models.Model):
    MONTHLY, DAILY, HOURLY = "monthly", "daily", "hourly"
    PAY_TYPES = [(MONTHLY, "Monthly salary"), (DAILY, "Day rate"), (HOURLY, "Hourly rate")]
    PAY_BY = [("cash", "Cash"), ("bank", "Bank transfer"), ("ecocash", "EcoCash / mobile money")]

    code = models.CharField("Staff no.", max_length=20, blank=True)
    first_name = models.CharField(max_length=60, blank=True)
    middle_name = models.CharField("Second name", max_length=60, blank=True)
    last_name = models.CharField("Surname", max_length=60, blank=True)
    known_as = models.CharField("Known as", max_length=60, blank=True,
                                help_text="The name everybody uses, e.g. Sidney or Welly. Leave empty if it is the first name.")
    id_number = models.CharField("National ID no.", max_length=40, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True, choices=[("F", "Female"), ("M", "Male")])
    job_title = models.CharField(max_length=80, blank=True)
    department = models.CharField(max_length=12, choices=DEPARTMENTS, default="production")
    phone = models.CharField("Cell", max_length=40, blank=True)
    address = models.CharField(max_length=200, blank=True)
    next_of_kin = models.CharField("Next of kin (name & cell)", max_length=150, blank=True)
    start_date = models.DateField("Started", default=datetime.date.today)
    end_date = models.DateField("Left on", null=True, blank=True)
    active = models.BooleanField("Still working here", default=True)

    pay_type = models.CharField(max_length=8, choices=PAY_TYPES, default=MONTHLY)
    rate = models.DecimalField("Salary / rate ($)", max_digits=10, decimal_places=2, default=Z,
                               help_text="Monthly salary, or pay per day, or pay per hour")
    transport_allowance = models.DecimalField("Transport allowance ($ / month)", max_digits=10, decimal_places=2,
                                              default=Z)
    other_allowance = models.DecimalField("Other allowance ($ / month)", max_digits=10, decimal_places=2, default=Z,
                                          help_text="Housing, meals, etc.")
    pays_nssa = models.BooleanField("Deduct NSSA", default=True)
    pays_paye = models.BooleanField("Deduct PAYE", default=True)
    nssa_no = models.CharField("NSSA no.", max_length=40, blank=True)
    tax_no = models.CharField("ZIMRA tax no. (TIN)", max_length=40, blank=True)
    paid_by = models.CharField("Paid by", max_length=8, choices=PAY_BY, default="cash")
    bank_details = models.CharField("Bank / EcoCash details", max_length=200, blank=True)
    leave_days = models.DecimalField("Leave days a year", max_digits=5, decimal_places=1, default=Decimal("22"))
    notes = models.TextField(blank=True)
    photo = models.FileField(storage=staff_storage, upload_to=photo_path, blank=True, max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active", "first_name", "last_name"]

    AVATAR = ["orange", "teal", "burgundy", "warm"]

    @property
    def initials(self):
        if self.is_open:
            return "?"
        parts = [p for p in ((self.known_as or self.first_name), self.last_name) if p.strip()]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        first = (self.known_as or self.first_name).strip()
        words = first.split()
        if len(words) >= 2:
            return (words[0][0] + words[-1][0]).upper()
        return first[:2].upper() or "?"

    @property
    def avatar_colour(self):
        return self.AVATAR[(self.pk or 0) % 4]

    @property
    def photo_v(self):
        """Changes whenever the record is saved, so the browser fetches a new photo."""
        return int(self.updated_at.timestamp()) if self.updated_at else 0

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        """A place for somebody we still have to employ: no name typed yet."""
        return not (self.first_name.strip() or self.known_as.strip())

    @property
    def short(self):
        return (self.known_as or self.first_name).strip() or "this person"

    @property
    def name(self):
        """What everybody calls them: Known as + surname (Sidney Ndlovu)."""
        if self.is_open:
            return f"Open – {self.job_title}" if self.job_title else "Open position"
        return f"{(self.known_as or self.first_name).strip()} {self.last_name}".strip()

    @property
    def full_name(self):
        """The name on the ID: first, second name and surname (Sydney Talent Ndlovu)."""
        if self.is_open:
            return self.name
        return " ".join(p.strip() for p in (self.first_name, self.middle_name, self.last_name) if p.strip())

    @property
    def allowances(self):
        return self.transport_allowance + self.other_allowance

    def open_advances(self):
        return self.advances.filter(recovered_in__isnull=True)

    def leave_balance(self, today=None):
        """Annual leave earned this year so far minus annual leave taken this year."""
        today = today or datetime.date.today()
        start = max(datetime.date(today.year, 1, 1), self.start_date)
        if start > today:
            return Z
        months = Decimal((today.year - start.year) * 12 + today.month - start.month + 1)
        earned = (self.leave_days * months / 12).quantize(Decimal("0.1"))
        taken = (self.leave.filter(kind="annual", start__year=today.year).aggregate(s=models.Sum("days"))["s"] or Z)
        return earned - taken


class Advance(models.Model):
    """Money given to a worker before pay day. Taken off the next pay run automatically."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="advances")
    date = models.DateField(default=datetime.date.today)
    amount = models.DecimalField("Amount ($)", max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=150, blank=True)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    recovered_in = models.ForeignKey("PayLine", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="advances_recovered")

    class Meta:
        ordering = ["-date", "-id"]


LEAVE_KINDS = [("annual", "Annual leave"), ("sick", "Sick leave"), ("maternity", "Maternity leave"),
               ("compassionate", "Compassionate / special"), ("unpaid", "Unpaid leave"), ("absent", "Absent (AWOL)")]


class LeaveRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave")
    kind = models.CharField("Type", max_length=14, choices=LEAVE_KINDS, default="annual")
    start = models.DateField("From")
    end = models.DateField("To (last day)")
    days = models.DecimalField("Working days", max_digits=5, decimal_places=1)
    notes = models.CharField(max_length=200, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")

    class Meta:
        ordering = ["-start"]


class PayRun(models.Model):
    DRAFT, FINAL = "draft", "final"
    STATUS = [(DRAFT, "Draft – still busy"), (FINAL, "Final – paid")]

    period = models.DateField("Month", help_text="Any day in the month; stored as the 1st")
    pay_date = models.DateField("Pay date")
    status = models.CharField(max_length=6, choices=STATUS, default=DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period", "-id"]

    def __str__(self):
        return f"Payroll {self.period:%B %Y}"

    @property
    def number(self):
        return f"PR-{self.pk:04d}"

    def totals(self):
        keys = ["basic", "overtime_pay", "allowances", "bonus", "other_earnings", "gross", "nssa", "paye", "aids_levy",
                "advances", "other_deductions", "net", "nssa_employer", "zimdef"]
        t = {k: Z for k in keys}
        n = 0
        for ln in self.lines.all():
            n += 1
            for k in keys:
                t[k] += getattr(ln, k)
        t["n"] = n
        t["tax"] = t["paye"] + t["aids_levy"]
        t["nssa_total"] = t["nssa"] + t["nssa_employer"]
        t["cost"] = t["gross"] + t["nssa_employer"] + t["zimdef"]
        return t


class PayLine(models.Model):
    run = models.ForeignKey(PayRun, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="pay_lines")
    # what was typed
    pay_type = models.CharField(max_length=8, choices=Employee.PAY_TYPES)
    rate = models.DecimalField(max_digits=10, decimal_places=2)
    days = models.DecimalField("Days worked", max_digits=5, decimal_places=2, null=True, blank=True)
    hours = models.DecimalField("Hours worked", max_digits=6, decimal_places=2, null=True, blank=True)
    unpaid_days = models.DecimalField("Unpaid days off", max_digits=5, decimal_places=2, default=Z)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Z)
    holiday_hours = models.DecimalField("Sunday / holiday hours", max_digits=6, decimal_places=2, default=Z)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    other_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    advances = models.DecimalField("Advances taken off", max_digits=10, decimal_places=2, default=Z)
    other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    deduction_note = models.CharField("Deduction note", max_length=100, blank=True)
    # worked out
    basic = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    overtime_pay = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    gross = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    nssa = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    taxable = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    paye = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    aids_levy = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    net = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    nssa_employer = models.DecimalField(max_digits=10, decimal_places=2, default=Z)
    zimdef = models.DecimalField(max_digits=10, decimal_places=2, default=Z)

    class Meta:
        ordering = ["run", "employee__first_name", "employee__last_name"]
        constraints = [models.UniqueConstraint(fields=["run", "employee"], name="one_line_per_employee_per_run")]

    @property
    def tax(self):
        return self.paye + self.aids_levy

    @property
    def total_deductions(self):
        return self.nssa + self.paye + self.aids_levy + self.advances + self.other_deductions


# ======================================================================= the staff file (personal papers)
PAPER_KINDS = [
    ("id", "National ID"), ("passport", "Passport"), ("permit", "Work / residence permit"), ("cv", "CV"),
    ("certificate", "Certificate / qualification"), ("medical", "Medical / food handler's certificate"),
    ("fingerprints", "Fingerprints"), ("contract", "Employment contract"), ("police", "Police clearance"),
    ("reference", "Reference letter"), ("bank", "Bank / EcoCash details"), ("nssa", "NSSA / ZIMRA papers"),
    ("warning", "Warning / disciplinary"), ("other", "Other"),
]
# What a complete staff file has. key, label, paper kinds that count for it
CHECKLIST = [
    ("id", "ID or passport", ("id", "passport")),
    ("contract", "Signed contract", ("contract",)),
    ("cv", "CV", ("cv",)),
    ("fingerprints", "Fingerprints", ("fingerprints",)),
    ("medical", "Medical certificate", ("medical",)),
    ("police", "Police clearance", ("police",)),
    ("certificate", "Certificates", ("certificate",)),
    ("reference", "Reference letter", ("reference",)),
    ("permit", "Work permit", ("permit",)),
]
SOON_DAYS = 30


def paper_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:8]
    return f"{instance.employee_id}/{instance.kind}-{datetime.date.today():%Y%m%d}-{uuid.uuid4().hex[:8]}{ext}"


class StaffPaper(models.Model):
    """One personal paper in a staff file: a scan or photo on the laptop (soft copy) and/or the paper in the file."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="papers")
    kind = models.CharField("Paper", max_length=14, choices=PAPER_KINDS, default="other")
    title = models.CharField("Description", max_length=120, blank=True,
                             help_text="Optional, e.g. 'front and back' or 'Certificate in Baking'")
    file = models.FileField(storage=staff_storage, upload_to=paper_path, blank=True, max_length=200)
    original_name = models.CharField(max_length=200, blank=True)
    size = models.PositiveIntegerField(default=0)
    hard_copy = models.BooleanField("The paper copy is in the staff file", default=False)
    expires = models.DateField("Expires on", null=True, blank=True,
                               help_text="Only for papers that run out: passport, permit, medical certificate …")
    notes = models.CharField(max_length=200, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "-added_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.employee}"

    @property
    def ext(self):
        return os.path.splitext(self.original_name or self.file.name)[1].lower().lstrip(".")

    @property
    def is_image(self):
        return self.ext in ("jpg", "jpeg", "png", "webp", "gif")

    def expiry_state(self, today=None):
        if not self.expires:
            return ""
        today = today or datetime.date.today()
        if self.expires < today:
            return "expired"
        if self.expires <= today + datetime.timedelta(days=SOON_DAYS):
            return "soon"
        return "ok"


def file_checklist(employee, needs, papers=None, today=None):
    """Each item of the staff file: is there a soft copy, is the paper in the file, has it run out?"""
    today = today or datetime.date.today()
    papers = list(employee.papers.all()) if papers is None else papers
    items = []
    for key, label, kinds in CHECKLIST:
        mine = [p for p in papers if p.kind in kinds]
        if key not in needs and not mine:
            continue
        soft = any(p.file for p in mine)
        hard = any(p.hard_copy for p in mine)
        # the paper that lasts longest counts (an ID that never runs out beats an old passport)
        ends = [p.expires for p in mine]
        best = None if (not ends or None in ends) else max(ends)
        state = "both" if soft and hard else "soft" if soft else "hard" if hard else "none"
        exp = ""
        if best and best < today:
            exp = "expired"
        elif best and best <= today + datetime.timedelta(days=SOON_DAYS):
            exp = "soon"
        items.append({"key": key, "label": label, "soft": soft, "hard": hard, "state": state, "required": key in needs,
                      "expires": best, "exp": exp, "kinds": kinds})
    return items


def expiring_papers(today=None):
    """Papers of people still working here that have run out, or run out within 30 days (newest one per kind)."""
    today = today or datetime.date.today()
    best = {}
    for p in StaffPaper.objects.filter(employee__active=True).select_related("employee"):
        k = (p.employee_id, p.kind)
        if k in best and (best[k].expires is None or (p.expires and p.expires <= best[k].expires)):
            continue
        best[k] = p
    out = [p for p in best.values() if p.expires and p.expires <= today + datetime.timedelta(days=SOON_DAYS)]
    return sorted(out, key=lambda p: p.expires)


@receiver(post_delete, sender=StaffPaper)
def _remove_paper_file(sender, instance, **kw):
    if instance.file:
        try:
            instance.file.storage.delete(instance.file.name)
        except OSError:
            pass


@receiver(post_delete, sender=Employee)
def _remove_photo_file(sender, instance, **kw):
    if instance.photo:
        try:
            instance.photo.storage.delete(instance.photo.name)
        except OSError:
            pass
