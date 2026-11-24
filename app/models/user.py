"""Modelo de usuarios y roles."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class User(db.Model):
    """Usuario que inicia sesión; también se asigna como director o responsable."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("admin", "usuario_proyecto", name="user_role"),
        nullable=False,
        default="usuario_proyecto",
    )
    company: Mapped[str | None] = mapped_column(String(160))
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def is_admin(self) -> bool:
        """Indica si el usuario tiene privilegios administrativos."""
        return self.role == "admin"

    def password_matches(self, text_input: str) -> bool:
        """Acceso concedido si el texto ingresado es igual a la contraseña guardada."""
        return text_input == self.password

    @classmethod
    def normalize_email(cls, email: str) -> str:
        """Normaliza emails para evitar duplicados por mayúsculas o espacios."""
        return email.strip().casefold()

