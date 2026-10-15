"""Django settings for the data quality API."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-data-quality-assistant")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").strip().lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["*"]
APPEND_SLASH = False

INSTALLED_APPS = [
    "quality",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "quality.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"


def _default_database_url() -> str:
    user = os.environ.get("USER") or "postgres"
    return f"postgresql+psycopg2://{user}@localhost:5432/data_quality"


def sqlalchemy_url(url: str) -> str:
    """Great Expectations expects a SQLAlchemy PostgreSQL URL."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def django_database(url: str) -> dict:
    parsed = urlparse(sqlalchemy_url(url).replace("postgresql+psycopg2://", "postgresql://", 1))
    query = parse_qs(parsed.query)
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 0,
    }
    options = {}
    if "sslmode" in query:
        options["sslmode"] = query["sslmode"][0]
    if options:
        config["OPTIONS"] = options
    return config


DATABASE_URL = sqlalchemy_url(os.environ.get("DATABASE_URL") or _default_database_url())
DATABASES = {"default": django_database(DATABASE_URL)}

SEED_DEMO_DATA = os.environ.get("SEED_DEMO_DATA", "false").strip().lower() in {"1", "true", "yes"}

# OpenAI is the provider for this project. Gemini and Groq stay available as optional switches.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
