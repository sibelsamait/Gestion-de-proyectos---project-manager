"""Modelos de KPI y gestión del cambio."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db

if TYPE_CHECKING:
    from .work import Milestone


class KpiDefinition(db.Model):
    """Definición configurable de un indicador."""

    __tablename__ = "kpi_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(
        Enum("project", "task", "milestone", "change", name="kpi_scope"), nullable=False
    )
    variables: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    formula: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    target: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    direction: Mapped[str] = mapped_column(
        Enum("higher", "lower", "range", name="kpi_direction"), nullable=False
    )
    thresholds: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    periodicity: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    source: Mapped[str] = mapped_column(
        Enum("automatic", "manual", name="kpi_source"), nullable=False, default="automatic"
    )
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    result: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    milestones: Mapped[list["Milestone"]] = relationship(
        secondary="milestone_kpis", back_populates="kpis"
    )


class KpiMeasurement(db.Model):
    """Medición histórica reproducible de un KPI."""

    __tablename__ = "kpi_measurements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kpi_id: Mapped[str] = mapped_column(ForeignKey("kpi_definitions.id", ondelete="CASCADE"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    result: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


milestone_kpis = db.Table(
    "milestone_kpis",
    db.Column(
        "milestone_id", db.String(36), db.ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True
    ),
    db.Column(
        "kpi_id", db.String(36), db.ForeignKey("kpi_definitions.id", ondelete="CASCADE"), primary_key=True
    ),
)


class ChangeRequest(db.Model):
    """Solicitud de cambio y estado de su flujo."""

    __tablename__ = "change_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    change_code: Mapped[str] = mapped_column(String(60), nullable=False)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    requested_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str | None] = mapped_column(Text)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    risk: Mapped[str] = mapped_column(String(20), nullable=False, default="medio")
    impact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="Registro")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    committed_date: Mapped[date | None] = mapped_column(Date)
    actual_date: Mapped[date | None] = mapped_column(Date)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    result: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(nullable=False, default=1)


class ChangeBaseline(db.Model):
    """Snapshot de fechas y costos antes de aplicar un cambio."""

    __tablename__ = "change_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    change_request_id: Mapped[str] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class ChangeApplication(db.Model):
    """Cambio individual aplicado con valor anterior y nuevo."""

    __tablename__ = "change_applications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    change_request_id: Mapped[str] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attribute: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
