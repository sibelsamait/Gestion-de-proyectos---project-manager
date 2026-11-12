"""Recálculo transaccional coordinado del estado de un proyecto."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    Resource,
    Task,
    TaskResourceAssignment,
)
from .costs import CostBreakdown, professional_overallocations, task_cost
from .kpi_engine import KpiError, evaluate_kpi
from .scheduler import recalculate_project


@dataclass(frozen=True)
class ProjectState:
    """Resultado del recálculo disponible para tableros y pruebas."""

    progress_percent: Decimal
    planned_cost: Decimal
    actual_cost: Decimal
    overallocated_professionals: dict[str, Decimal]


def _cost_totals(session: Session, tasks: list[Task]) -> tuple[Decimal, Decimal]:
    """Suma costos planificados y reales de todas las tareas."""
    planned = Decimal(0)
    actual = Decimal(0)
    for task in tasks:
        breakdown: CostBreakdown = task_cost(session, task.id)
        planned += breakdown.planned
        actual += breakdown.actual
    return planned.quantize(Decimal("0.01")), actual.quantize(Decimal("0.01"))


def _kpi_values(
    session: Session,
    project_id: str,
    tasks: list[Task],
    milestones: list[Milestone],
    planned_cost: Decimal,
    actual_cost: Decimal,
) -> dict[str, Decimal]:
    """Construye el registro común de variables automáticas."""
    total = Decimal(len(tasks))
    completed = sum((Decimal(str(task.progress_percent)) for task in tasks), Decimal(0))
    overdue = sum(
        1
        for task in tasks
        if task.planned_end and task.planned_end < date.today() and task.progress_percent < 100
    )
    professional_ids = select(Resource.id).where(
        Resource.project_id == project_id, Resource.type == "Profesional"
    )
    assigned = session.scalar(
        select(func.coalesce(func.sum(Resource.hours_per_week * TaskResourceAssignment.planned_units), 0))
        .join(TaskResourceAssignment, TaskResourceAssignment.resource_id == Resource.id)
        .where(Resource.id.in_(professional_ids))
    ) or Decimal(0)
    available = session.scalar(
        select(func.coalesce(func.sum(Resource.hours_per_week), 0)).where(
            Resource.project_id == project_id, Resource.type == "Profesional"
        )
    ) or Decimal(0)
    changes_total = Decimal(
        session.scalar(
            select(func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project_id)
        )
        or 0
    )
    changes_approved = Decimal(
        session.scalar(
            select(func.count(ChangeRequest.id)).where(
                ChangeRequest.project_id == project_id,
                ChangeRequest.status == "approved",
            )
        )
        or 0
    )
    on_time = Decimal(sum(1 for milestone in milestones if milestone.status == "cumplido"))
    overdue_milestones = Decimal(sum(1 for milestone in milestones if milestone.status == "vencido"))
    return {
        "trabajo_completado": completed,
        "trabajo_total": total,
        "hitos_en_plazo": on_time,
        "hitos_vencidos": overdue_milestones,
        "costo_real": actual_cost,
        "costo_planificado": planned_cost,
        "tareas_atrasadas": Decimal(overdue),
        "tareas_evaluadas": total,
        "horas_asignadas": Decimal(str(assigned)),
        "horas_disponibles": Decimal(str(available)),
        "cambios_aprobados": changes_approved,
        "cambios_totales": changes_total,
    }


def _refresh_automatic_kpis(
    session: Session,
    project_id: str,
    values: dict[str, Decimal],
) -> None:
    """Actualiza KPI automáticos dentro de la misma transacción."""
    definitions = session.scalars(
        select(KpiDefinition).where(
            KpiDefinition.project_id == project_id,
            KpiDefinition.source == "automatic",
        )
    ).all()
    for kpi in definitions:
        if not set(kpi.variables or []).issubset(values):
            raise KpiError(f"El KPI {kpi.code} usa una variable no disponible.")
        if (
            values.get("trabajo_total") == 0
            and "trabajo_total" in (kpi.variables or [])
        ) or (
            values.get("cambios_totales") == 0
            and "cambios_totales" in (kpi.variables or [])
        ):
            continue
        evaluate_kpi(session, kpi, {name: values[name] for name in kpi.variables})


def recalculate_project_state(session: Session, project_id: str) -> ProjectState:
    """Recalcula dependencias, costos, avance, alertas y KPI atómicamente.

    La función no hace commit. El llamador debe confirmar todo o ejecutar
    rollback si cualquier etapa genera una excepción.
    """
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError("El proyecto no existe.")
    recalculate_project(project_id, session)
    tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
    milestones = session.scalars(select(Milestone).where(Milestone.project_id == project_id)).all()
    progress = (
        sum((Decimal(str(task.progress_percent)) for task in tasks), Decimal(0))
        / Decimal(len(tasks))
        if tasks
        else Decimal(0)
    ).quantize(Decimal("0.01"))
    planned_cost, actual_cost = _cost_totals(session, tasks)
    project.progress_percent = progress
    values = _kpi_values(session, project_id, tasks, milestones, planned_cost, actual_cost)
    _refresh_automatic_kpis(session, project_id, values)
    return ProjectState(
        progress_percent=progress,
        planned_cost=planned_cost,
        actual_cost=actual_cost,
        overallocated_professionals=professional_overallocations(session, project_id),
    )
