"""Django settings for the NSE price platform."""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

def _setting(name, default):
    value = os.environ.get(name, "").strip()
    return value or default


SECRET_KEY = _setting("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = _setting("DJANGO_DEBUG", "False") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "market",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _setting("POSTGRES_DB", "nse"),
        "USER": _setting("POSTGRES_USER", "nse"),
        "PASSWORD": _setting("POSTGRES_PASSWORD", "nse"),
        "HOST": _setting("POSTGRES_HOST", "db"),
        "PORT": _setting("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_ENGINE = "django.contrib.sessions.backends.db"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True


def _origin(value):
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


_csrf_origins = []
_csrf_raw = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if not _csrf_raw:
    _csrf_raw = "http://localhost:9011,http://127.0.0.1:9011"
for _piece in _csrf_raw.split(","):
    _cleaned = _origin(_piece)
    if _cleaned and _cleaned not in _csrf_origins:
        _csrf_origins.append(_cleaned)
for _local in (
    "http://localhost:9011",
    "http://127.0.0.1:9011",
    "http://localhost:9012",
    "http://127.0.0.1:9012",
):
    if _local not in _csrf_origins:
        _csrf_origins.append(_local)
CSRF_TRUSTED_ORIGINS = _csrf_origins

DATA_DIR = Path(_setting("DATA_DIR", "/app/data"))
LIVE_FEED_START = "2026-10-28"

CELERY_BROKER_URL = _setting("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

YEARLY_PRICE_FILES = [
    "NSE_data_all_stocks_2023.csv",
    "NSE_data_all_stocks_2024.csv",
    "NSE_data_all_stocks_2025.csv",
    "NSE_data_all_stocks_2026_upto_jun.csv",
]
