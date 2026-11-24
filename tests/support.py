"""Utilidades compartidas por las pruebas."""

from datetime import UTC, datetime

from app.extensions import db
from app.models import User


def create_user(app, email="persona@example.com", name="Persona Demo", role="usuario_proyecto"):
    """Registra una persona directamente en la base y devuelve su id."""
    with app.app_context():
        user = User(name=name, email=email, role=role, terms_accepted_at=datetime.now(UTC))
        user.password = "una-clave-segura-123"
        db.session.add(user)
        db.session.commit()
        return user.id
