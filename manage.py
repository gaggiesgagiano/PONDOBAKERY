#!/usr/bin/env python
"""Pondo Bakery – command-line helper (used by Start Pondo and for maintenance)."""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "vendor"))

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pondo_site.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
