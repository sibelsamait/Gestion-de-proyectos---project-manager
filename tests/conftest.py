"""Fixtures de pruebas de Fase 1."""

import pytest

from app import create_app
from app.config import Config
from app.extensions import db


class TestConfig(Config):
    """Configuración aislada para pruebas."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


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
def anon_client(app):
    """Cliente sin sesión iniciada."""
    return app.test_client()


@pytest.fixture
def client(app):
    """Cliente con sesión iniciada como administrador."""
    from support import create_user

    user_id = create_user(app, "tester@example.com", "Tester", role="admin")
    test_client = app.test_client()
    with test_client.session_transaction() as session:
        session["user_id"] = user_id
    return test_client

