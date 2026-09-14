"""
Phahendra Babu Library — Django settings.

Environment-driven configuration. Defaults allow a quick local run with
SQLite + console email; production uses PostgreSQL + Redis + SMTP.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Load backend/.env first (production on PythonAnywhere), then fall back to a
# project-root .env for local development. Override stays off, so whichever
# file exists first wins.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

# ------------------------------------------------------------------ Security
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
if not DEBUG and (SECRET_KEY == "dev-insecure-secret-change-me" or len(SECRET_KEY) < 32):
    raise RuntimeError(
        "DJANGO_SECRET_KEY must be set to a strong, unique value when DEBUG=False."
    )
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "DJANGO_CORS_ORIGINS",
        # www + http variants are included so phones that reach the site via
        # "www." or before the HTTPS redirect are not blocked (a blocked
        # request surfaces as a generic "Network Error" in the browser).
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://phagendrababulibrary.in,https://www.phagendrababulibrary.in,"
        "http://phagendrababulibrary.in,http://www.phagendrababulibrary.in",
    ).split(",")
    if o.strip()
]
# Credentials are not needed for bearer-JWT auth; keep cookies on the same-origin
# admin only by leaving credentials disabled for cross-origin API calls.
CORS_ALLOW_CREDENTIALS = os.getenv("DJANGO_CORS_CREDENTIALS", "False").lower() in ("1", "true")
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Only trust X-Forwarded-For (used for audit logs + rate limiting) when the
# app sits behind a reverse proxy you control. Off by default so clients
# cannot spoof their IP.
TRUST_X_FORWARDED_FOR = os.getenv("DJANGO_TRUST_XFF", "False").lower() in ("1", "true")
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SSL_REDIRECT", "True").lower() in ("1", "true")
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# ------------------------------------------------------------------- Apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    "django_extensions",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.library",
    "apps.memberships",
    "apps.seats",
    "apps.notifications",
    "apps.analytics",
    "apps.reviews",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.accounts.middleware.AuditLogMiddleware",
    "apps.accounts.middleware.RateLimitMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------- Database
# For PythonAnywhere FREE plan, optimize SQLite for better concurrency
# while maintaining PostgreSQL compatibility for VPS upgrades
if os.getenv("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "libseat"),
            "USER": os.getenv("POSTGRES_USER", "libseat"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", "libseat"),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "connect_timeout": 10,
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                # SQLite timeout optimization for better concurrency handling
                "timeout": 30,
            },
            "CONN_MAX_AGE": 0,  # SQLite doesn't benefit from connection pooling
        }
    }

# Cache: prefer Redis when explicitly configured, else fall back to local memory
# so throttling/sessions keep working even without a running Redis instance.
_redis_url = os.getenv("REDIS_URL", "")
if os.getenv("CHANNEL_BACKEND", "").lower() == "memory" or not _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "OPTIONS": {"db": 0},
        }
    }

# ------------------------------------------------------------------ Auth
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TTL_MINUTES", "30"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TTL_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ALGORITHM": "HS256",
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    # Adjusted throttle rates for FREE plan - prevents abuse while allowing legitimate usage
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",  # Reduced from 120 for FREE plan
        "user": "300/minute",  # Reduced from 600 for FREE plan
        "auth": "5/minute",  # Reduced from 10 for FREE plan
        "otp": "3/minute",  # Reduced from 5 for FREE plan
        "reviews": "20/hour",  # public review submissions — spam guard
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# ----------------------------------------------------------------- Spectacular
SPECTACULAR_SETTINGS = {
    "TITLE": "Phahendra Babu Library API",
    "DESCRIPTION": "Premium 3D Library Seat Booking Platform",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ------------------------------------------------------------------ Celery
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
# Emails go through Celery only when a Redis broker is actually configured.
# Without Redis (local dev, free-tier hosts) the same helpers send inline, so
# behaviour is unchanged and nothing is silently dropped.
USE_CELERY = bool(os.getenv("REDIS_URL"))

# Default periodic jobs. django-celery-beat also allows ad-hoc entries from the
# admin UI; both sources are merged by beat at runtime.
CELERY_BEAT_SCHEDULE = {
    "expire-stale-holds": {
        "task": "apps.seats.tasks.expire_hold_bookings",
        "schedule": timedelta(seconds=60),
    },
    "expire-overdue-memberships": {
        "task": "apps.memberships.tasks.expire_memberships_task",
        "schedule": timedelta(minutes=5),
    },
    "expire-cash-requests": {
        "task": "apps.memberships.tasks.expire_cash_payment_requests",
        "schedule": timedelta(minutes=5),
    },
    "membership-reminders": {
        "task": "apps.memberships.tasks.run_membership_reminders",
        "schedule": timedelta(hours=1),
    },
}

# ------------------------------------------------------------------ Static
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# WhiteNoise optimization for FREE plan
WHITENOISE_USE_FINDERS = True
WHITENOISE_MAX_AGE = 31536000  # 1 year for static files
WHITENOISE_IMMUTABLE_FILE_TYPES = (
    'application/javascript',
    'image/x-icon',
    'image/jpeg',
    'image/png',
    'image/svg+xml',
    'text/css',
    'text/plain',
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ Email
# Use SMTP automatically once EMAIL_HOST_USER is configured; otherwise fall
# back to the console backend so local development keeps working without
# credentials (emails are printed to the runserver log).
_email_backend_override = os.getenv("EMAIL_BACKEND", "")
_email_user = os.getenv("EMAIL_HOST_USER", "")
if _email_backend_override:
    EMAIL_BACKEND = _email_backend_override
elif _email_user:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = _email_user
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("1", "true")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Phahendra Babu Library <no-reply@phahendrababulibrary.example>")

# ------------------------------------------------------------------ Payments
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
# Webhook secret from the Razorpay Dashboard (Settings → Webhooks). Webhook
# deliveries are HMAC-verified against this; empty disables webhook handling.
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

# Simulated gateway / mock payments for local demo. These MUST stay disabled
# outside local demo environments or anyone can mark payments paid.
ALLOW_MOCK_PAYMENTS = os.getenv("ALLOW_MOCK_PAYMENTS", "True").lower() in ("1", "true")
if not DEBUG:
    ALLOW_MOCK_PAYMENTS = False

# ------------------------------------------------------------------- Google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

# ------------------------------------------------------------------- SMS
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

# --------------------------------------------------------------- Frontend
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# ------------------------------------------------------------------- Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose" if DEBUG else "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO" if not DEBUG else "DEBUG",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO" if not DEBUG else "DEBUG",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",  # Reduce DB query logging in production
            "propagate": False,
        },
        "libseat": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
