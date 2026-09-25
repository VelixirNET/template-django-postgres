"""
Settings for the guestbook, read from the environment.

The same file serves your laptop and velixir: everything that differs arrives as an
environment variable. On velixir the important ones are injected for you (PORT,
VELIXIR_APP_SLUG and, once a managed Postgres is bound, DATABASE_URL), so a fresh deploy
needs no configuration at all.

The build imports this file too, to collect static files, with no database and no secrets.
That is why nothing below may require either.
"""

import hashlib
import hmac
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name):
    """A comma-separated environment variable as a list, blanks dropped."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# ─── Database ───────────────────────────────────────────────────────────────

# velixir injects DATABASE_URL as postgres://user:pass@host:5432/db?sslmode=require.
# dj-database-url turns it into Django's DATABASES shape and puts sslmode in OPTIONS, where
# psycopg hands it to libpq. libpq's "require" is exactly what velixir means: encrypt the
# connection, but do not check the certificate against public CAs (it comes from velixir's
# own CA). No TLS code needed, unlike node-postgres.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# No database bound yet. The app still starts, and every page explains how to bind one
# (guestbook/middleware.py). A crash loop would read as "the platform is broken".
SETUP_MODE = not DATABASE_URL

if SETUP_MODE:
    DATABASES = {}
else:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            # Reuse connections between requests rather than paying for a TLS handshake on
            # every page, and check one before reusing it, so a database restart costs a
            # failed check instead of a failed page.
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
    # Give up after five seconds when the database is unreachable, instead of hanging the
    # request (and the health check) while the kernel retries the connection.
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault("connect_timeout", 5)


# ─── Secret key ─────────────────────────────────────────────────────────────

# Django signs sessions, password reset links and flash messages with SECRET_KEY, so the key
# must be the same in every process that serves the app, and across restarts. That rules
# out the tempting shortcut of a fresh random key on each boot:
#
#   * Every restart would sign everyone out and void every reset link. On the Free plan the
#     app restarts each time it wakes from sleep.
#   * Each process would hold a different key. With two replicas, or gunicorn workers that
#     import settings separately, a login handled by one is rejected by the next, and people
#     are signed out at random.
#
# So, in order:
#   1. DJANGO_SECRET_KEY, when set. Set one if the key should outlive a change of database
#      password.
#   2. Derived from DATABASE_URL. The URL already carries a secret (the database password)
#      that is identical in every process and never leaves the platform. An HMAC turns it
#      into a key without exposing it: knowing the key does not reveal the password.
#      Rotating the database password rotates the key, which signs everyone out once.
#   3. No database at all (the build, or setup mode): a placeholder. In setup mode every page
#      is the setup page, so nothing is ever signed with it.
def _secret_key():
    configured = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if configured:
        return configured
    if DATABASE_URL:
        return hmac.new(
            DATABASE_URL.encode(), b"velixir django-postgres SECRET_KEY", hashlib.sha256
        ).hexdigest()
    return "setup-mode-placeholder-not-a-secret-never-signs-real-traffic"


SECRET_KEY = _secret_key()

# Off unless asked for. The debug page shows settings and source code to anyone who triggers
# an error, so it must never switch on for a public URL by accident.
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"


# ─── Hosts, and the proxy in front ──────────────────────────────────────────

# velixir's edge passes the public hostname through in Host: <slug>.velixir.run, or a custom
# domain. ".velixir.run" (leading dot: any subdomain) covers the app's own address without
# knowing the slug in advance. Custom domains go in DJANGO_ALLOWED_HOSTS, comma-separated:
# example.com,www.example.com (or .example.com for every subdomain).
CUSTOM_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
ALLOWED_HOSTS = [".velixir.run", "localhost", "127.0.0.1", *CUSTOM_HOSTS]

# A form POST passes Django's CSRF check when its Origin header matches the scheme and host
# Django thinks the request used. Behind the edge that scheme comes from X-Forwarded-Proto,
# which says https on most routes but can say http on others, while the browser's Origin
# always says https. Trusting the origins explicitly makes the check pass either way, so no
# form ever fails with "CSRF verification failed" because of the route it took.
CSRF_TRUSTED_ORIGINS = ["https://*.velixir.run"] + [
    f"https://*{host}" if host.startswith(".") else f"https://{host}"
    for host in CUSTOM_HOSTS
    if host != "*"
]

# The edge terminates TLS and forwards plain HTTP, saying which scheme the visitor used in
# X-Forwarded-Proto. Nothing but the edge can reach the app, so the header can be trusted.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Never redirect to HTTPS from inside the app. The edge already does it for plain-HTTP
# visitors, and on a route where the header says http, the app would send an HTTPS visitor
# to the very URL they asked for: a redirect loop. `manage.py check --deploy` suggests turning
# it on (security.W008), so that suggestion is silenced here rather than followed.
SECURE_SSL_REDIRECT = False
SILENCED_SYSTEM_CHECKS = ["security.W008"]

# Visitors always reach the app over HTTPS, so its cookies can insist on it. Relaxed with
# DJANGO_DEBUG=1, for plain http://localhost during development.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG


# ─── Application ────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    # First, so its templates win: it adds a first-run hint to the admin's login page.
    "guestbook",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    # First, so /healthz is answered before anything checks the Host header. The platform's
    # health probe addresses the container by its IP, which is not an allowed host.
    "guestbook.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # Serves /static/ from the image. Ahead of the setup page, so that page has its assets.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Switches itself off once a database is bound. Until then, every page is the setup page.
    "guestbook.middleware.SetupModeMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # A database that drops out mid-request gets a 503 that says so, not a bare 500.
    "guestbook.middleware.DatabaseUnavailableMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Outbound SMTP is blocked on velixir (web traffic only), so Django's default SMTP backend
# cannot send. Nothing here sends mail yet; when you need to, use an HTTPS email API through
# a backend such as django-anymail. Until then, mail is printed to the log.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ─── Static files ───────────────────────────────────────────────────────────

# collectstatic runs during the build (nixpacks.toml) and writes everything to STATIC_ROOT,
# each file with a content hash in its name and a compressed copy beside it. WhiteNoise
# serves them from the image with far-future cache headers, which is safe because a changed
# file gets a new name. That covers your own CSS and JavaScript and the admin's.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    # Uploaded files (a FileField, an ImageField) would land on the container's disk, which
    # is wiped on every deploy. Point this at a bucket (django-storages) before adding one.
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}


# ─── Logging ────────────────────────────────────────────────────────────────

# Everything to stderr, which is what velixir collects. Django's default only prints to the
# console with DEBUG on, so without this a 500 in production would leave no trace at all.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{levelname} {name}: {message}", "style": "{"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["stderr"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["stderr"], "level": "INFO", "propagate": False},
    },
}
