"""Private storage for staff photos and personal papers (ID, passport, CV, certificates …).

The files live in data\\staff_files, apart from the product photos. They have no public link: the program
only hands them out to someone who is logged in and has staff rights (see staff/files.py).
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class StaffStorage(FileSystemStorage):
    @property
    def base_location(self):
        return str(settings.STAFF_FILES_DIR)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Staff files have no public link – open them through the staff pages.")


def staff_storage():
    return StaffStorage()
