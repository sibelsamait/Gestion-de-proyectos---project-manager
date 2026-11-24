"""Configuración centralizada y segura."""

import os
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
    RATES_API_URL = os.environ.get("RATES_API_URL", "https://mindicador.cl/api")
    CRON_SECRET = os.environ.get("CRON_SECRET", "")
