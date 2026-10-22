"""Backups: an automatic copy on the laptop, and a copy to a flash drive on request."""
import os
import sqlite3
import string
import sys
from pathlib import Path

from django.conf import settings
from django.utils import timezone

KEEP_LOCAL = 30


def _copy_db(dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(settings.DATABASES["default"]["NAME"]))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)  # safe copy, even while the program is running
    dst.close()
    src.close()
    return dest


def _stamp():
    return timezone.localtime().strftime("%Y-%m-%d_%H%M")


def make_local_backup(reason="auto"):
    dest = settings.BACKUP_DIR / f"pondo_{_stamp()}_{reason}.sqlite3"
    _copy_db(dest)
    old = sorted(settings.BACKUP_DIR.glob("pondo_*.sqlite3"))
    for f in old[:-KEEP_LOCAL]:
        try:
            f.unlink()
        except OSError:
            pass
    return dest


def flash_drives():
    """Removable drives (flash drives) plugged into this Windows laptop."""
    test = os.environ.get("PONDO_TEST_DRIVE")
    if test:
        return [test]
    if not sys.platform.startswith("win"):
        return []
    import ctypes

    found = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if bitmask & (1 << i):
            root = f"{letter}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) == 2:  # DRIVE_REMOVABLE
                found.append(root)
    return found


def copy_photos(folder):
    """Product photos (data\\media) go next to the backups, in a 'photos' folder. Only new or changed ones are copied."""
    import shutil

    src = Path(settings.MEDIA_ROOT)
    n = 0
    if not src.exists():
        return n
    for f in src.rglob("*"):
        if f.is_file():
            to = folder / "photos" / f.relative_to(src)
            if not to.exists() or to.stat().st_size != f.stat().st_size:
                to.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, to)
                n += 1
    return n


def copy_staff_files(folder):
    """Staff photos and papers (data\\staff_files) go into a 'staff files' folder, with a list of whose file is whose.
    Only new or changed ones are copied. These are personal papers – keep the flash drive locked away."""
    import csv
    import shutil

    src = Path(settings.STAFF_FILES_DIR)
    n = 0
    if not src.exists():
        return n
    to_root = folder / "staff files"
    for f in src.rglob("*"):
        if f.is_file():
            to = to_root / f.relative_to(src)
            if not to.exists() or to.stat().st_size != f.stat().st_size:
                to.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, to)
                n += 1
    try:
        from staff.models import Employee, StaffPaper

        to_root.mkdir(parents=True, exist_ok=True)
        with open(to_root / "list of staff files.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["Staff no.", "Name", "Paper", "Description", "Original file name", "Paper copy in file",
                        "Runs out", "File in this folder"])
            for e in Employee.objects.exclude(photo=""):
                w.writerow([e.code, e.name, "Photo", "", "", "", "", e.photo.name.replace("/", "\\")])
            for p in StaffPaper.objects.select_related("employee").order_by("employee__code", "employee__first_name", "kind"):
                w.writerow([p.employee.code, p.employee.name, p.get_kind_display(), p.title, p.original_name,
                            "yes" if p.hard_copy else "no", p.expires or "", p.file.name.replace("/", "\\") if p.file else ""])
    except OSError:
        pass
    return n


def backup_to_drive(root):
    folder = Path(root) / "Pondo Backups"
    dest = folder / f"pondo_{_stamp()}.sqlite3"
    _copy_db(dest)
    copy_photos(folder)
    copy_staff_files(folder)
    return dest


# ------------------------------------------------------------------ online (server): one zip with everything
KEEP_NIGHTLY = 14


def make_zip(dest_dir=None, reason="nightly"):
    """A zip with the database, product photos, staff files and the signature – everything needed to restore Pondo."""
    import tempfile
    import zipfile

    dest_dir = Path(dest_dir or (settings.BACKUP_DIR / "nightly"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"pondo_{_stamp()}_{reason}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        db = _copy_db(Path(tmp) / "pondo.sqlite3")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db, "pondo.sqlite3")
            for folder, arc in ((settings.MEDIA_ROOT, "media"), (settings.STAFF_FILES_DIR, "staff_files"),
                                (settings.DATA_DIR / "signatures", "signatures")):
                folder = Path(folder)
                if folder.exists():
                    for f in folder.rglob("*"):
                        if f.is_file():
                            z.write(f, f"{arc}/{f.relative_to(folder).as_posix()}")
    keep = KEEP_NIGHTLY if reason == "nightly" else 2
    if True:
        for f in sorted(dest_dir.glob(f"pondo_*_{reason}.zip"))[:-keep]:
            try:
                f.unlink()
            except OSError:
                pass
    return dest


def nightly_zips():
    folder = settings.BACKUP_DIR / "nightly"
    return sorted(folder.glob("pondo_*_nightly.zip"), reverse=True) if folder.exists() else []
