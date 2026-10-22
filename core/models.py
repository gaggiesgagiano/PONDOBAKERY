from decimal import Decimal

from django.conf import settings
from django.db import models


class Shop(models.Model):
    """A Pondo shop. One for now – the program is ready for more later."""

    name = models.CharField(max_length=100, default="Pondo Bakery")
    address_line1 = models.CharField("Address line 1", max_length=150, blank=True)
    address_line2 = models.CharField("Address line 2 / town", max_length=150, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    email = models.CharField(max_length=120, blank=True)
    tin = models.CharField("TIN no.", max_length=80, blank=True)
    vat_no = models.CharField("VAT / registration no.", max_length=80, blank=True)
    payment_details = models.TextField("Payment details (printed on invoices)", blank=True,
                                       help_text="Bank name, account number, branch, EcoCash merchant code …")
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CompanySettings(models.Model):
    """Settings that apply to the whole business (one row)."""

    company_name = models.CharField(max_length=100, default="Pondo Bakery")
    vat_rate = models.DecimalField("VAT rate", max_digits=6, decimal_places=4, default=Decimal("0.155"),
                                   help_text="0.155 = 15.5%")
    target_gp = models.DecimalField("Target gross profit", max_digits=6, decimal_places=4, default=Decimal("0.60"),
                                    help_text="0.60 = 60%")
    gp_low = models.DecimalField("GP warning below", max_digits=6, decimal_places=4, default=Decimal("0.35"),
                                 help_text="Products below this GP show red")
    profit_target = models.DecimalField("Profit I want per month ($)", max_digits=12, decimal_places=2,
                                        default=Decimal("15000"))
    trading_days = models.PositiveSmallIntegerField("Trading days per week", default=6)
    waste_target = models.DecimalField("Waste target (maximum)", max_digits=6, decimal_places=4,
                                       default=Decimal("0.05"), help_text="0.05 = 5% of sales")
    zwg_rate = models.DecimalField("ZWG per US$1", max_digits=10, decimal_places=4, null=True, blank=True,
                                   help_text="The rate the till uses for ZWG (ZiG) payments – every sale from the moment you save")
    zwg_rate_at = models.DateTimeField(null=True, blank=True)
    gp_override = models.DecimalField("GP % for the dashboard", max_digits=6, decimal_places=4, null=True,
                                      blank=True, help_text="Empty = the average GP of your products")
    last_flash_backup = models.DateTimeField(null=True, blank=True)
    last_flash_backup_to = models.CharField(max_length=200, blank=True)
    backup_waived_on = models.DateField(null=True, blank=True)
    stock_usage = models.CharField("Stock is used up by", max_length=12, default="sales",
                                   choices=[("sales", "Till sales + waste"), ("production", "Production plans marked Done")])
    stock_variance_limit = models.DecimalField("Explain stock take differences from ($)", max_digits=10, decimal_places=2,
                                               default=Decimal("100"))  # the Manager opened Pondo without yesterday's backup
    # look & feel (the business default – each person can pick their own under "My look")
    theme = models.CharField(max_length=20, default="classic")
    heading_font = models.CharField(max_length=20, default="retro")
    text_size = models.CharField(max_length=10, default="normal")
    pattern = models.BooleanField("Bakery pattern in the menu", default=True)
    greeting = models.BooleanField("Friendly greeting on the dashboard", default=True)
    brand_font = models.CharField("Pondo font file", max_length=120, blank=True)
    tagline = models.CharField(max_length=60, default="Easy to enjoy", blank=True)

    class Meta:
        verbose_name_plural = "company settings"

    def __str__(self):
        return "Settings"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class ChangeLog(models.Model):
    """Who changed what, and when."""

    when = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    area = models.CharField(max_length=60)
    item = models.CharField(max_length=200)
    action = models.CharField(max_length=30)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-when"]

    def __str__(self):
        return f"{self.when:%d %b %Y %H:%M} {self.user} {self.action} {self.item}"


class Overhead(models.Model):
    """Monthly running costs (rent, ZESA, gas …) – used for break-even on the dashboard."""

    name = models.CharField(max_length=80)
    monthly_cost = models.DecimalField("Monthly cost ($)", max_digits=12, decimal_places=2, default=Decimal("0"))
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


def log_change(user, area, item, action, details=""):
    ChangeLog.objects.create(user=user if getattr(user, "is_authenticated", False) else None,
                             area=area, item=str(item)[:200], action=action, details=details)


class Access(models.Model):
    """Rights for one (non-owner) user. 0 = no access, 1 = can look, 2 = can look & change."""

    LEVELS = [(0, "No access"), (1, "Can look"), (2, "Can look & change")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access")
    role = models.CharField(max_length=20, blank=True)
    recipes = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    ingredients = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    prices = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    production = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    stock = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    sales = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    staff = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    money = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    invoices = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    deliveries = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    waste = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    equipment = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    letters = models.PositiveSmallIntegerField(choices=LEVELS, default=0)
    sops = models.PositiveSmallIntegerField(choices=LEVELS, default=1)
    see_costs = models.BooleanField("See costs & profit", default=False)
    backup = models.BooleanField("Make flash drive backups", default=False)

    def __str__(self):
        return f"Rights for {self.user}"

    @classmethod
    def from_preset(cls, user, key):
        from .access import PRESETS

        p = PRESETS[key]
        acc, _ = cls.objects.get_or_create(user=user)
        from .access import AREAS

        for area, *_ in AREAS:
            setattr(acc, area, p["levels"].get(area, 0))
        acc.see_costs, acc.backup, acc.role = p["see_costs"], p["backup"], key
        acc.save()
        return acc


class UserLook(models.Model):
    """A person's own look (empty = same as the business) and the jobs they want on their dashboard."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="look")
    theme = models.CharField(max_length=20, blank=True)
    heading_font = models.CharField(max_length=20, blank=True)
    text_size = models.CharField(max_length=10, blank=True)
    pattern = models.CharField(max_length=3, blank=True)   # "", "on", "off"
    greeting = models.CharField(max_length=3, blank=True)  # "", "on", "off"
    jobs = models.TextField(blank=True, default="")  # today's jobs in order, e.g. "sales,cashup,my:3"; empty = standard list

    def __str__(self):
        return f"Look for {self.user}"


class MyJob(models.Model):
    """A job somebody added to Today's jobs themselves, e.g. 'Clean the display fridges'. Ticked off each day."""

    COLOURS = [("orange", "Pondo Orange"), ("teal", "Teal"), ("burgundy", "Burgundy"), ("warm", "Warm Orange")]
    DAYS = [("0", "Mon"), ("1", "Tue"), ("2", "Wed"), ("3", "Thu"), ("4", "Fri"), ("5", "Sat"), ("6", "Sun")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="my_jobs")
    title = models.CharField("Job", max_length=60)
    note = models.CharField("Small line under it", max_length=80, blank=True)
    link = models.CharField("Opens the page", max_length=20, blank=True)
    days = models.CharField(max_length=7, default="0123456")
    colour = models.CharField(max_length=10, choices=COLOURS, default="teal")
    shared = models.BooleanField("For everybody", default=False,
                                 help_text="Everybody sees it; when one person ticks it, it is done for all.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    @property
    def key(self):
        return f"my:{self.pk}"

    @property
    def days_text(self):
        if self.days == "0123456":
            return "every day"
        if self.days == "012345":
            return "Monday to Saturday"
        if self.days == "01234":
            return "weekdays"
        names = dict(self.DAYS)
        return ", ".join(names[d] for d in self.days)


class MyJobDone(models.Model):
    job = models.ForeignKey(MyJob, on_delete=models.CASCADE, related_name="done")
    date = models.DateField()
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "date"], name="one_tick_per_job_per_day")]


class EmailSettings(models.Model):
    """How Pondo sends e-mail (one row). The password is stored scrambled with this laptop's secret key."""

    SSL, TLS, NONE = "ssl", "tls", "none"
    host = models.CharField("Outgoing mail server (SMTP)", max_length=120, blank=True,
                            help_text="From the e-mail host, usually mail.pondobakery.co.zw")
    port = models.PositiveIntegerField(default=465, help_text="465 with SSL, or 587 with STARTTLS")
    security = models.CharField(max_length=4, default=SSL,
                                choices=[(SSL, "SSL (port 465)"), (TLS, "STARTTLS (port 587)"), (NONE, "None")])
    username = models.CharField("Username", max_length=120, blank=True, default="jurie@pondobakery.co.zw",
                                help_text="Usually the full e-mail address")
    password_enc = models.TextField(blank=True)
    from_name = models.CharField("Send as (name)", max_length=80, default="Pondo Bakery")
    from_email = models.CharField("From e-mail address", max_length=120, default="jurie@pondobakery.co.zw")
    copy_me = models.BooleanField("Send me a copy (BCC) of every e-mail", default=True)
    accountant_email = models.CharField("Accountant's e-mail", max_length=200, blank=True,
                                        help_text="Filled in when you e-mail the accountant report. Several: separate with commas.")
    signature = models.TextField("Signature under every e-mail", blank=True, default=(
        "Kind regards\nJurie Gagiano\nOperations Manager · Pondo Bakery\n+263 78 048 9777 · jurie@pondobakery.co.zw\n"
        "74 Chinhoyi Street, Harare · pondobakery.co.zw"))
    last_test = models.DateTimeField(null=True, blank=True)
    last_test_ok = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "e-mail settings"

    def __str__(self):
        return "E-mail settings"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        return obj or cls.objects.create()

    @property
    def ready(self):
        return bool(self.host and self.username and self.password_enc and self.from_email)


class EmailLog(models.Model):
    """Every e-mail Pondo sent (or tried to send)."""

    when = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    what = models.CharField(max_length=120)
    to = models.CharField(max_length=300)
    subject = models.CharField(max_length=200)
    attachments = models.CharField(max_length=300, blank=True)
    ok = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-when"]


class Letter(models.Model):
    """A letter typed in Pondo and printed on the letterhead (page 1) – kept so it can be printed again."""

    date = models.DateField()
    to = models.TextField("To", blank=True, help_text="Name, company and address – one per line")
    subject = models.CharField("Subject", max_length=200, blank=True)
    body = models.TextField("Letter", help_text="Start with the greeting (Dear …). Ctrl+B bold, Ctrl+I italics, Ctrl+U underline.")
    sign_name = models.CharField("Signed by", max_length=100, blank=True)
    sign_title = models.CharField("Job title", max_length=100, blank=True)
    add_signature = models.BooleanField("Add Jurie's signature", default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} {self.subject or 'Letter'}"

    @property
    def number(self):
        return f"LT-{self.pk:04d}" if self.pk else "LT-new"

    @property
    def to_first_line(self):
        return (self.to or "").strip().split("\n")[0].strip()

    def body_html(self):
        """The letter as safe HTML paragraphs (bold / italic / underline kept)."""
        from .richtext import clean, from_plain
        b = self.body or ""
        return clean(b) if "<" in b else from_plain(b)

    def paragraphs(self):
        """The letter text split on empty lines (single line breaks stay inside a paragraph)."""
        import re
        text = (self.body or "").replace("\r\n", "\n").strip()
        return [p.strip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()]


# ======================================================================= SOP file
SOP_SECTIONS = [(1, "Opening & closing"), (2, "Cash, tills & cash-up"), (3, "Production & baking"),
                (4, "Food safety & hygiene"), (5, "Stock, orders & receiving"), (6, "Customer service & sales"),
                (7, "Staff & HR"), (8, "Health, safety & emergencies")]


class Sop(models.Model):
    """One standard operating procedure. Job titles only – no names – so the file works for other shops too."""
    DRAFT, APPROVED = "draft", "approved"

    section = models.PositiveSmallIntegerField(choices=SOP_SECTIONS)
    seq = models.PositiveSmallIntegerField("Number in the section")
    title = models.CharField(max_length=150)
    purpose = models.TextField("Purpose", help_text="One or two sentences: why we do it this way")
    responsible = models.CharField("Responsible (job titles)", max_length=200, blank=True,
                                   help_text="e.g. Supervisor on duty · Cashiers – titles, never names")
    applies = models.CharField("Must be read by", max_length=120, default="all",
                               help_text="Departments whose staff must read and sign this SOP")
    body = models.TextField("Procedure")
    status = models.CharField(max_length=10, default=DRAFT, choices=[(DRAFT, "Draft"), (APPROVED, "Approved")])
    version = models.PositiveIntegerField(default=1)
    written_by = models.CharField(max_length=100, default="Manager")
    approved_by = models.CharField(max_length=100, default="Owner / Director")
    approved_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["section", "seq", "id"]

    def __str__(self):
        return f"{self.code} {self.title}"

    @property
    def code(self):
        return f"SOP {self.section}.{self.seq:02d}"

    @property
    def section_name(self):
        return dict(SOP_SECTIONS).get(self.section, "")

    @property
    def review_due(self):
        if not self.approved_on:
            return None
        try:
            return self.approved_on.replace(year=self.approved_on.year + 1)
        except ValueError:                       # 29 February
            return self.approved_on.replace(year=self.approved_on.year + 1, day=28)

    def applies_keys(self):
        return [k for k in self.applies.split(",") if k]

    def applies_text(self):
        from staff.models import DEPARTMENTS
        keys = self.applies_keys()
        if "all" in keys or not keys:
            return "All staff"
        names = dict(DEPARTMENTS)
        return " · ".join(names.get(k, k) for k in keys)

    def readers(self):
        """Active staff who must read this SOP (open positions left out)."""
        from staff.models import Employee
        qs = Employee.objects.filter(active=True)
        keys = self.applies_keys()
        if keys and "all" not in keys:
            qs = qs.filter(department__in=keys)
        return [e for e in qs.order_by("department", "last_name", "first_name") if not e.is_open]


class SopVersion(models.Model):
    """An earlier version of an SOP, kept when an approved SOP is changed."""
    sop = models.ForeignKey(Sop, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=150)
    purpose = models.TextField()
    responsible = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    approved_on = models.DateField(null=True, blank=True)
    approved_by = models.CharField(max_length=100, blank=True)
    saved_at = models.DateTimeField(auto_now_add=True)
    saved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField("What changed", max_length=200, blank=True)

    class Meta:
        ordering = ["-version"]


class SopRead(models.Model):
    """A staff member signed that they read and understood an SOP (the version they read is kept)."""
    sop = models.ForeignKey(Sop, on_delete=models.CASCADE, related_name="reads")
    employee = models.ForeignKey("staff.Employee", on_delete=models.CASCADE, related_name="sop_reads")
    version = models.PositiveIntegerField()
    signed_on = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("sop", "employee")]


class LoginRecord(models.Model):
    """Every log-in, log-out and wrong password: who, when and from where (which computer / phone)."""
    IN, OUT, FAILED = "in", "out", "failed"

    when = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    username = models.CharField(max_length=150, blank=True)
    event = models.CharField(max_length=6, choices=[(IN, "Logged in"), (OUT, "Logged out"), (FAILED, "Wrong password")])
    ip = models.CharField("Address", max_length=60, blank=True)
    device = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-when", "-id"]

    @property
    def where(self):
        ip = self.ip or ""
        if ip in ("127.0.0.1", "::1", "localhost"):
            return "Main computer"
        if ip.startswith(("192.168.", "10.")) or any(ip.startswith(f"172.{n}.") for n in range(16, 32)):
            return f"Shop network · {ip}"
        return f"Outside · {ip}" if ip else "–"


class StaffCard(models.Model):
    """A staff card with a barcode: scan to log in and to approve on the till. Holds a random code, never the password."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="card",
                                help_text="The Pondo login this card opens (empty = card only, e.g. for the staff account later)")
    employee = models.OneToOneField("staff.Employee", null=True, blank=True, on_delete=models.CASCADE, related_name="staff_card")
    code = models.CharField(max_length=20, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"Card of {self.employee or self.user}"
