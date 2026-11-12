"""Modelo de usuarios y roles."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db, login_manager

if TYPE_CHECKING:
    from .project import ProjectMembership


class User(UserMixin, db.Model):
    """Usuario mínimo con rol y consentimiento legal."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum("admin", "usuario_proyecto", "solo_lectura", name="user_role"),
        nullable=False,
        default="usuario_proyecto",
    )
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        """Indica si el usuario tiene privilegios administrativos."""
        return self.role == "admin"

    def set_password(self, password: str) -> None:
        """Almacena un hash resistente, nunca la contraseña."""
        if len(password) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres.")
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        """Verifica una contraseña contra su hash."""
        return check_password_hash(self.password_hash, password)

    @classmethod
    def normalize_email(cls, email: str) -> str:
        """Normaliza emails para evitar duplicados por mayúsculas o espacios."""
        return email.strip().casefold()


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    """Carga el usuario autenticado desde la sesión."""
    return db.session.get(User, user_id)
