"""Fixtures de pruebas de Fase 1."""

import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    """Configuración aislada para pruebas."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TALISMAN_FORCE_HTTPS = False


@pytest.fixture
def app():
    """Aplicación con base SQLite efímera."""
    application = create_app(TestConfig)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Cliente HTTP de pruebas."""
    return app.test_client()

