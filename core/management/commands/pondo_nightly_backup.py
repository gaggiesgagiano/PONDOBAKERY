"""python manage.py pondo_nightly_backup – run every night by the server (scheduled task). Keeps the last 14."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Make the nightly backup zip of Pondo (database, photos, staff files)."

    def handle(self, *args, **options):
        from core.backup import make_zip
        self.stdout.write(f"Backup saved: {make_zip()}")
