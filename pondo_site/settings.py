"""Settings for the Pondo Bakery program (runs locally on the bakery laptop)."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PONDO_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_key_file = DATA_DIR / "secret.key"
if not _key_file.exists():
    _key_file.write_text(secrets.token_urlsafe(50))
SECRET_KEY = _key_file.read_text().strip()

DEBUG = os.environ.get("PONDO_DEBUG") == "1"
# Other computers in the shop (and the boss through the private Tailscale link) reach Pondo by this computer's
# name or network address, so every address is accepted. Everyone still has to log in.
ALLOWED_HOSTS = ["*"]

# ONLINE: Pondo on a server on the internet (set PONDO_ONLINE=1 and PONDO_HOSTS=pondo.pondobakery.co.zw,… on the server)
ONLINE = os.environ.get("PONDO_ONLINE") == "1"
if ONLINE:
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("PONDO_HOSTS", "").split(",") if h.strip()] or ["*"]
    CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h != "*"]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_REFERRER_POLICY = "same-origin"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "core",
    "costing",
    "production",
    "stock",
    "sales",
    "till",
    "fiscal",
    "staff",
    "reports",
    "invoices",
    "equipment",
    "money",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.LoginRequiredMiddleware",
    "core.middleware.DailyBackupLockMiddleware",
    "core.middleware.PrivateFontMiddleware",
]

ROOT_URLCONF = "pondo_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context.shop",
            ],
        },
    },
]

WSGI_APPLICATION = "pondo_site.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "pondo.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Harare"
USE_I18N = False
USE_TZ = True
USE_THOUSAND_SEPARATOR = False

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"
# ZIMRA fiscal engine (FiscalStackZW.dll + PondoFiscalBridge.exe). See fiscal_engine\\README - Pondo fiscal.txt
FISCAL_ENGINE_DIR = Path(os.environ.get("PONDO_FISCAL_ENGINE_DIR", BASE_DIR / "fiscal_engine"))
FISCAL_MONO = os.environ.get("PONDO_FISCAL_MONO", "")   # only for running the engine on Linux (tests)

# Staff photos and personal papers: kept apart from the media folder and only opened through the program.
STAFF_FILES_DIR = DATA_DIR / "staff_files"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_AGE = 60 * 60 * 12  # log out after 12 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The DEMO copy ("Start DEMO (practice copy).bat") runs next to the real Pondo on the same computer.
# Browsers share cookies between the two, so the demo uses its own cookie names – logging in to one
# never logs you out of the other.
if os.environ.get("PONDO_DEMO") == "1":
    SESSION_COOKIE_NAME = "pondo_demo_session"
    CSRF_COOKIE_NAME = "pondo_demo_csrftoken"
