"""Modelos de proyectos y su lista de usuarios por rol."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Project(db.Model):
    """Proyecto al que se aplican las reglas de aislamiento."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    objectives: Mapped[str | None] = mapped_column(Text)
    director_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sponsor: Mapped[str | None] = mapped_column(String(160))
    authorized_budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        Enum("planificado", "en_ejecucion", "suspendido", "terminado", name="project_status"),
        nullable=False,
        default="planificado",
    )
    # Ciclo de vida: la preinversión (estudios, evaluación, autorización) precede a la inversión.
    phase: Mapped[str] = mapped_column(
        Enum("preinversion", "inversion", name="project_phase"), nullable=False, default="preinversion"
    )
    # Documento formal que autoriza el desarrollo y designa al Director(a) del proyecto.
    authorized_by: Mapped[str | None] = mapped_column(String(160))
    authorization_date: Mapped[date | None] = mapped_column(Date)
    authorization_reference: Mapped[str | None] = mapped_column(String(160))
    authorization_notes: Mapped[str | None] = mapped_column(Text)
    # Estrategia de monitoreo y control de la ejecución.
    control_plan: Mapped[str | None] = mapped_column(Text)
    # Evaluación económica para inversionistas y bancos.
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=10)
    evaluation_years: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectMember.added_at"
    )


PROJECT_ROLES = ("admin", "gestor", "miembro")
# Miembro solo lee y exporta el PDF; las acciones exigen gestor o admin.
ROLE_RANK = {"miembro": 1, "gestor": 2, "admin": 3}


class ProjectMember(db.Model):
    """Correo autorizado en un proyecto con su rol; puede existir antes de que la persona se registre."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "email", name="uq_project_member_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Enum(*PROJECT_ROLES, name="project_role"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="members")
