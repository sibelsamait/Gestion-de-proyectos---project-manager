"""Configuración centralizada y segura."""

import os
from datetime import timedelta
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_database_url(url: str) -> str:
    """Normaliza URLs de PostgreSQL y exige TLS en producción."""
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    if url.startswith("postgresql+psycopg2://"):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.setdefault("sslmode", "require")
        url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    return url


class Config:
    """Valores comunes; los secretos siempre provienen del entorno."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.environ.get("DATABASE_URL", "sqlite:///project_manager.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"poolclass": __import__("sqlalchemy").pool.NullPool}
        if os.environ.get("FLASK_ENV") == "production"
        else {}
    )
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATES_API_URL = os.environ.get("RATES_API_URL", "https://mindicador.cl/api")
    CRON_SECRET = os.environ.get("CRON_SECRET", "")
    TALISMAN_FORCE_HTTPS = os.environ.get("FLASK_ENV") == "production"
    CONTENT_SECURITY_POLICY: ClassVar[dict] = {
        "default-src": "'self'",
        "img-src": ["'self'", "data:"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
    }
