# ─────────────────────────────────────────────────────────────────────────────
# ADD THIS BLOCK to the BOTTOM of your settings.py
# (langgamit_backend/langgamit_backend/settings.py)
# ─────────────────────────────────────────────────────────────────────────────

import os
import dj_database_url
from datetime import timedelta

# ── Secret key & debug ────────────────────────────────────────────────────────
# In development: keep your hardcoded key in settings.py
# On Render:      we override with the SECRET_KEY env var set in the dashboard

SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)   # falls back to dev key
DEBUG      = os.environ.get("DEBUG", "True") == "True"  # False on Render

# ── Allowed hosts ──────────────────────────────────────────────────────────────
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
]

# Render automatically injects RENDER_EXTERNAL_HOSTNAME
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)

# ── Database ───────────────────────────────────────────────────────────────────
# CRITICAL: Use persistent PostgreSQL database, NOT free tier
# Free tier databases on Render are ephemeral and get deleted periodically
# 
# Render injects DATABASE_URL for the linked PostgreSQL service.
# Locally this variable is absent so Django uses the default SQLite config
# you already have above this block.

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            # Ensure connections are properly recycled
            options={
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000'
            }
        )
    }
else:
    # Fallback to SQLite for local development
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
        }
    }

# ── Static files (WhiteNoise) ──────────────────────────────────────────────────
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATIC_URL  = "/static/"

# Insert WhiteNoise right after SecurityMiddleware
_security_idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(_security_idx + 1, "whitenoise.middleware.WhiteNoiseMiddleware")

if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ── CORS ───────────────────────────────────────────────────────────────────────
# Add your deployed frontend URL here once you deploy it
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",    # Vite dev
    "http://localhost:3000",    # CRA / Next.js dev
    "https://langgam-it-by-keybeen.vercel.app",  # Frontend (NO trailing slash!)
]

# Allow credentials (cookies, auth headers) in CORS requests
CORS_ALLOW_CREDENTIALS = True

# ── Logging ───────────────────────────────────────────────────────────────────
# Log database connection issues for debugging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# ── Sessions ──────────────────────────────────────────────────────────────────
# Store sessions in the database (PostgreSQL in production)
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS only in production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# ── JWT (same as before, explicit here for reference) ─────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":    timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME":   timedelta(days=1),
    "ROTATE_REFRESH_TOKENS":    True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES":        ("Bearer",),
    "UPDATE_LAST_LOGIN":        True,
}