"""Staff numbers, photos, personal papers (soft and hard copy), prints and the backup of staff files."""
import datetime
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import Access

from .models import Employee, PayrollSettings, StaffPaper, expiring_papers, file_checklist
from .numbers import next_number, number_everyone

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 200
PDF = b"%PDF-1.4\n%fake\n"


class StaffFileTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ov = override_settings(STAFF_FILES_DIR=Path(self.tmp) / "staff_files")
        self.ov.enable()
        self.owner = User.objects.create_superuser("owner", password="TestPass123!")
        self.client.force_login(self.owner)
        d = datetime.date(2020, 1, 1)
        self.ann = Employee.objects.create(first_name="Ann", last_name="Moyo", start_date=d + datetime.timedelta(days=300))
        self.ben = Employee.objects.create(first_name="Ben", start_date=d)
        self.cat = Employee.objects.create(first_name="Cat", start_date=d + datetime.timedelta(days=300))

    def tearDown(self):
        self.ov.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cashier(self):
        u = User.objects.create_user("till", password="x")
        Access.from_preset(u, "cashier")
        self.client.force_login(u)

    def upload(self, emp, files, **data):
        data.setdefault("kind", "id")
        return self.client.post(f"/staff/{emp.pk}/papers/add/", {**data, "files": files})

    # ---------------------------------------------------------------- numbers
    def test_numbers_year_started_and_never_reused(self):
        today = datetime.date.today()
        yy = f"{today.year % 100:02d}"
        self.assertEqual(next_number(), f"{yy}001")
        r = self.client.get("/staff/")
        self.assertContains(r, "Give them numbers")
        self.client.post("/staff/files/numbers/")
        codes = {e.first_name: e.code for e in Employee.objects.all()}
        self.assertEqual(codes, {"Ben": "20001", "Ann": "20002", "Cat": "20003"})  # started 2020, longest-serving first
        Employee.objects.filter(pk=self.cat.pk).update(active=False)  # Cat leaves – her number stays hers
        self.assertEqual(next_number(start=datetime.date(2020, 5, 1)), "20004")
        r = self.client.get("/staff/new/")
        self.assertContains(r, f'placeholder="{yy}001 – given when you save"')
        base = {"department": "shop", "pay_type": "monthly", "transport_allowance": "0", "other_allowance": "0",
                "paid_by": "cash", "leave_days": "22", "active": "on"}
        r = self.client.post("/staff/new/", {**base, "first_name": "Dan", "code": "", "start_date": f"{today.year}-01-05", "rate": "300"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Employee.objects.get(first_name="Dan").code, f"{yy}001")  # given when left empty
        r = self.client.post("/staff/new/", {**base, "first_name": "Eve", "code": "", "start_date": "2019-03-01", "rate": "300"})
        self.assertEqual(Employee.objects.get(first_name="Eve").code, "19001")
        # pay must be at least $1
        r = self.client.post("/staff/new/", {**base, "first_name": "Fay", "code": "", "start_date": "2026-01-05", "rate": "0.01"})
        self.assertContains(r, "at least $1")

    def test_number_must_be_unique_and_letters_style(self):
        number_everyone()
        r = self.client.post(f"/staff/{self.ann.pk}/edit/", {"first_name": "Ann", "code": "20001", "department": "shop",
                                                             "start_date": "2020-10-27", "pay_type": "monthly", "rate": "300",
                                                             "transport_allowance": "0", "other_allowance": "0",
                                                             "paid_by": "cash", "leave_days": "22", "active": "on"})
        self.assertContains(r, "already Ben")
        self.client.post("/staff/files/settings/", {"staff_no_style": "prefix", "staff_no_prefix": "pb-",
                                                    "staff_no_digits": "3", "needs": ["id", "cv"]})
        s = PayrollSettings.get()
        self.assertEqual((s.staff_no_style, s.staff_no_prefix, s.staff_no_digits, s.needs), ("prefix", "PB-", 3, ["id", "cv"]))
        self.assertEqual(next_number(), "PB-001")
        self.client.post("/staff/files/settings/", {"staff_no_style": "prefix", "staff_no_prefix": "PB1", "staff_no_digits": "3"})
        self.assertEqual(PayrollSettings.get().staff_no_prefix, "PB-")  # can't end in a number
        self.client.post("/staff/files/settings/", {"staff_no_style": "year", "staff_no_prefix": "", "staff_no_digits": "3"})
        self.assertEqual(next_number(start=datetime.date(2020, 1, 1)), "20004")

    def test_advance_at_least_one_dollar(self):
        from .models import Advance

        self.client.post(f"/staff/{self.ann.pk}/advance/", {"date": "2026-10-01", "amount": "0.50", "reason": "x"})
        self.assertFalse(Advance.objects.exists())
        self.client.post(f"/staff/{self.ann.pk}/advance/", {"date": "2026-10-01", "amount": "1", "reason": "x"})
        self.assertEqual(Advance.objects.count(), 1)
        r = self.client.get(f"/staff/{self.ann.pk}/")
        self.assertContains(r, 'step="any"')

    def test_search_and_sort(self):
        number_everyone()
        r = self.client.get("/staff/?q=20003")
        self.assertContains(r, "Cat")
        self.assertNotContains(r, ">Ben<")
        r = self.client.get("/staff/?sort=no")
        html = r.content.decode()
        self.assertLess(html.index("20001"), html.index("20002"))

    # ---------------------------------------------------------------- photo
    def test_photo_upload_private_and_checked(self):
        r = self.client.post(f"/staff/{self.ann.pk}/photo/change/", {"photo": SimpleUploadedFile("me.jpg", JPEG)})
        self.assertEqual(r.status_code, 302)
        self.ann.refresh_from_db()
        path = Path(settings.STAFF_FILES_DIR) / self.ann.photo.name
        self.assertTrue(path.exists())
        self.assertNotIn(str(settings.MEDIA_ROOT), str(path))  # not in the public media folder
        r = self.client.get(f"/staff/{self.ann.pk}/photo/")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/jpeg"))
        self.assertEqual(self.client.get(f"/media/{self.ann.photo.name}").status_code, 404)
        # a text file pretending to be a photo is refused
        self.client.post(f"/staff/{self.ben.pk}/photo/change/", {"photo": SimpleUploadedFile("x.jpg", b"hello")})
        self.ben.refresh_from_db()
        self.assertFalse(self.ben.photo)
        # changing the photo removes the old file
        self.client.post(f"/staff/{self.ann.pk}/photo/change/", {"photo": SimpleUploadedFile("new.png", b"\x89PNG\r\n\x1a\n" + b"0" * 50)})
        self.assertFalse(path.exists())
        self.client.post(f"/staff/{self.ann.pk}/photo/change/", {"remove": "1"})
        self.ann.refresh_from_db()
        self.assertFalse(self.ann.photo)

    def test_cashier_cannot_see_photos_or_papers(self):
        self.client.post(f"/staff/{self.ann.pk}/photo/change/", {"photo": SimpleUploadedFile("me.jpg", JPEG)})
        self.upload(self.ann, [SimpleUploadedFile("id.pdf", PDF)])
        p = StaffPaper.objects.get()
        self.cashier()
        for url in (f"/staff/{self.ann.pk}/photo/", f"/staff/papers/{p.pk}/", "/staff/files/", "/staff/cards/print/",
                    f"/staff/{self.ann.pk}/file/print/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertEqual(r.url, "/", url)

    # ---------------------------------------------------------------- papers
    def test_papers_soft_and_hard_copy(self):
        r = self.upload(self.ann, [SimpleUploadedFile("front.jpg", JPEG), SimpleUploadedFile("back.jpg", JPEG)], title="ID")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(sorted(StaffPaper.objects.values_list("title", flat=True)), ["ID (1 of 2)", "ID (2 of 2)"])
        self.upload(self.ann, [], kind="contract", hard_copy="on")  # only the paper copy, no scan yet
        self.upload(self.ann, [SimpleUploadedFile("cv.docx", b"PK..")], kind="cv")
        self.upload(self.ann, [SimpleUploadedFile("virus.exe", b"MZ")], kind="other")
        self.upload(self.ann, [], kind="cv")  # nothing chosen, nothing ticked
        self.assertEqual(StaffPaper.objects.count(), 4)
        items = {i["key"]: i["state"] for i in file_checklist(self.ann, PayrollSettings.get().needs)}
        self.assertEqual(items, {"id": "soft", "contract": "hard", "cv": "soft", "fingerprints": "none", "medical": "none"})
        front = StaffPaper.objects.filter(kind="id").first()
        self.client.post(f"/staff/papers/{front.pk}/hard/")
        self.assertEqual(file_checklist(self.ann, ["id"])[0]["state"], "both")
        r = self.client.get(f"/staff/{self.ann.pk}/")
        self.assertContains(r, "Staff file")
        self.assertContains(r, "ID (1 of 2)")

    def test_open_download_and_delete(self):
        self.upload(self.ann, [SimpleUploadedFile("scan.pdf", PDF)], kind="passport")
        self.upload(self.ann, [SimpleUploadedFile("cv.docx", b"PK..")], kind="cv")
        pdf, doc = StaffPaper.objects.get(kind="passport"), StaffPaper.objects.get(kind="cv")
        r = self.client.get(f"/staff/papers/{pdf.pk}/")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r["Content-Disposition"].startswith("inline"))
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("Ann Moyo - Passport.pdf", r["Content-Disposition"])
        self.assertTrue(self.client.get(f"/staff/papers/{pdf.pk}/?download=1")["Content-Disposition"].startswith("attachment"))
        self.assertTrue(self.client.get(f"/staff/papers/{doc.pk}/")["Content-Disposition"].startswith("attachment"))
        path = Path(settings.STAFF_FILES_DIR) / pdf.file.name
        self.assertTrue(path.exists())
        self.client.post(f"/staff/papers/{pdf.pk}/delete/")
        self.assertFalse(path.exists())
        self.assertFalse(StaffPaper.objects.filter(pk=pdf.pk).exists())

    def test_expiry_warnings(self):
        today = datetime.date.today()
        self.upload(self.ann, [SimpleUploadedFile("old.pdf", PDF)], kind="passport", expires=str(today - datetime.timedelta(days=5)))
        self.upload(self.ben, [SimpleUploadedFile("med.pdf", PDF)], kind="medical", expires=str(today + datetime.timedelta(days=10)))
        self.assertEqual({p.employee.first_name for p in expiring_papers()}, {"Ann", "Ben"})
        self.assertEqual(file_checklist(self.ann, ["id"])[0]["exp"], "expired")
        r = self.client.get("/")
        self.assertContains(r, "Staff papers")
        self.assertContains(r, "1 ran out")
        # a new passport replaces the old one: no more warning
        self.upload(self.ann, [SimpleUploadedFile("new.pdf", PDF)], kind="passport", expires=str(today + datetime.timedelta(days=3000)))
        self.assertEqual([p.employee.first_name for p in expiring_papers()], ["Ben"])
        self.assertEqual(file_checklist(self.ann, ["id"])[0]["exp"], "")

    # ---------------------------------------------------------------- prints & backup
    def test_prints(self):
        number_everyone()
        self.upload(self.ann, [SimpleUploadedFile("id.pdf", PDF)], hard_copy="on")
        r = self.client.get(f"/staff/{self.ann.pk}/file/print/")
        self.assertContains(r, "Staff file")
        self.assertContains(r, "20002")
        self.assertContains(r, "ID or passport")
        self.assertEqual(self.client.get("/staff/files/print/").status_code, 200)
        r = self.client.get("/staff/cards/print/?colour=warm")
        self.assertContains(r, "20001")
        self.assertContains(r, "primary_reverse_burgundy.svg")
        self.assertContains(self.client.get(f"/staff/{self.ann.pk}/card/print/"), "Ann Moyo")
        self.assertContains(self.client.get("/staff/files/"), "Everybody working here")

    def test_flash_drive_backup_takes_staff_files(self):
        from core import backup

        number_everyone()
        self.client.post(f"/staff/{self.ann.pk}/photo/change/", {"photo": SimpleUploadedFile("me.jpg", JPEG)})
        self.upload(self.ann, [SimpleUploadedFile("id.pdf", PDF)])
        drive = Path(self.tmp) / "drive"
        n = backup.copy_staff_files(drive / "Pondo Backups")
        self.assertEqual(n, 2)
        listing = (drive / "Pondo Backups" / "staff files" / "list of staff files.csv").read_text(encoding="utf-8-sig")
        self.assertIn("20002,Ann Moyo,National ID", listing)
        self.assertIn("Photo", listing)
