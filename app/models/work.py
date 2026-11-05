"""Modelos de tareas, recursos, calendario e hitos."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db


class Task(db.Model):
    """Tarea plana de un proyecto."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_task_progress"),
        CheckConstraint("planned_duration_days >= 0", name="ck_task_planned_duration"),
        CheckConstraint("actual_duration_days >= 0", name="ck_task_actual_duration"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    etapa: Mapped[str | None] = mapped_column(String(120))
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    planned_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    dependencies_out: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.predecessor_id", back_populates="predecessor", cascade="all, delete-orphan"
    )
    dependencies_in: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.successor_id", back_populates="successor", cascade="all, delete-orphan"
    )


class TaskDependency(db.Model):
    """Relación de precedencia entre dos tareas."""

    __tablename__ = "task_dependencies"

    predecessor_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    successor_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    dependency_type: Mapped[str] = mapped_column(
        Enum("FS", "SS", "FF", "SF", name="dependency_type"), nullable=False, default="FS"
    )
    lag_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predecessor: Mapped[Task] = relationship(foreign_keys=[predecessor_id], back_populates="dependencies_out")
    successor: Mapped[Task] = relationship(foreign_keys=[successor_id], back_populates="dependencies_in")


class NonWorkingDay(db.Model):
    """Día no laborable configurable por proyecto."""

    __tablename__ = "non_working_days"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(160))


class Resource(db.Model):
    """Recurso valorizable asignable a tareas."""

    __tablename__ = "resources"
    __table_args__ = (
        CheckConstraint("hourly_rate >= 0", name="ck_resource_hourly_rate"),
        CheckConstraint("quantity >= 0", name="ck_resource_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_resource_unit_cost"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        Enum("Profesional", "Licencia", "Material", "Equipamiento", "Otros", name="resource_type"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(120))
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    hours_per_week: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    weeks: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, default=0)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)


class TaskResourceAssignment(db.Model):
    """Asignación de recurso a una tarea."""

    __tablename__ = "task_resource_assignments"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True)
    planned_units: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    actual_units: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)


class Milestone(db.Model):
    """Hito de duración cero asociado a tareas."""

    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    committed_date: Mapped[date | None] = mapped_column(Date)
    actual_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        Enum("pendiente", "en_progreso", "cumplido", "vencido", name="milestone_status"),
        nullable=False,
        default="pendiente",
    )
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
