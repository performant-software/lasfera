import os
from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
env = environ.Env()
READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=True)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))
IS_HEROKU_APP = "DYNO" in os.environ and "CI" not in os.environ

env = environ.FileAwareEnv(
    DEBUG=(bool, False),
)

# GENERAL
# ------------------------------------------------------------------------------

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)
SQL_DEBUG = env.bool("SQL_DEBUG", default=False)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="django-insecure )$-$@6=%dtoet5l+p@-ug)mwssbtclfz*sua+ni+1llkw4lr)o",
)

TIME_ZONE = "America/New_York"
LANGUAGE_CODE = "en-us"
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost"]
)
X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019"]

# Application definition

INSTALLED_APPS = [
    "accounts",
    "manuscript",
    "textannotation",
    "map",
    "pages",
    "gallery",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "admin_interface",
    "colorfield",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.messages",
    "prose",
    "django_prose_editor",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "fontawesomefree",
    "tailwind",
    "theme",
    "import_export",
    "django_dbml",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Django doesn't support serving static assets in a production-ready way, so we use the
    # excellent WhiteNoise package to do so instead. The WhiteNoise middleware must be listed
    # after Django's `SecurityMiddleware` so that security redirects are still performed.
    # See: https://whitenoise.readthedocs.io
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

if DEBUG:
    # only enable django_browser_reload during development
    INSTALLED_APPS += ["django_browser_reload"]
    MIDDLEWARE += ["django_browser_reload.middleware.BrowserReloadMiddleware"]

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
                "django.template.context_processors.request",
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
if IS_HEROKU_APP:
    # In production on Heroku the database configuration is derived from the `DATABASE_URL`
    # environment variable by the dj-database-url package. `DATABASE_URL` will be set
    # automatically by Heroku when a database addon is attached to your Heroku app. See:
    # https://devcenter.heroku.com/articles/provisioning-heroku-postgres#application-config-vars
    # https://github.com/jazzband/dj-database-url
    DATABASES = {
        "default": dj_database_url.config(
            env="DATABASE_URL",
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        ),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("DB_HOST", default="localhost"),
            "PORT": env("DB_PORT", default="5432"),
            "NAME": env("DB_NAME", default="lasfera"),
            "USER": env("DB_USER", default="lasfera"),
            "PASSWORD": env("DB_PASS", default="password"),
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
# AUTH_USER_MODEL = "accounts.CustomUser"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Error logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if SQL_DEBUG else "INFO",
            "propagate": False,
        },
    },
}

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = "en-us"

USE_I18N = True

USE_TZ = True

# User authentication
LOGIN_REDIRECT_URL = "/admin/"

DATA_UPLOAD_MAX_NUMBER_FIELDS = 15240

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

if IS_HEROKU_APP:
    # use s3 storage to prevent uploads to heroku ephemeral storage
    AWS_ACCESS_KEY_ID = env.str("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env.str("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_QUERYSTRING_AUTH = False 
    AWS_S3_FILE_OVERWRITE = False
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        # Enable WhiteNoise's GZip (and Brotli, if installed) compression of static assets:
        # https://whitenoise.readthedocs.io/en/latest/django.html#add-compression-and-caching-support
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
    WHITENOISE_KEEP_ONLY_HASHED_FILES = True
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    MEDIA_URL = "/media/"

MEDIA_ROOT = str(BASE_DIR / "media")

ADMINS = [
    ("Jason Heppler", "jheppler@gmu.edu"),
]
MANAGERS = ADMINS

# Wagtail settings
WAGTAIL_SITE_NAME = "La Sfera"
WAGTAILADMIN_BASE_URL = "https://dev.lasfera.rrchnm.org"
WAGTAILDOCS_EXTENSIONS = [
    "csv",
    "docx",
    "key",
    "odt",
    "pdf",
    "rtf",
    "txt",
    "xlsx",
]
TAGGIT_CASE_INSENSITIVE = True

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tailwind CSS
TAILWIND_APP_NAME = "theme"
INTERNAL_IPS = [
    "127.0.0.1",
]
