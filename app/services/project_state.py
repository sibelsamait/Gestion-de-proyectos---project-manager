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
    earned_value: dict[str, Decimal]


STANDARD_PROJECT_KPIS = (
    {
        "code": "AVANCE",
        "name": "Avance del proyecto",
        "objective": "Mide cuánto trabajo de las actividades está terminado.",
        "variables": ["trabajo_completado", "trabajo_total"],
        "formula": "trabajo_completado / trabajo_total * 100",
        "unit": "%",
        "target": Decimal(100),
        "direction": "higher",
        "thresholds": {"green": 90, "yellow": 70},
    },
    {
        "code": "HITOS",
        "name": "Cumplimiento de hitos",
        "objective": "Mide el porcentaje de hitos cumplidos.",
        "variables": ["hitos_en_plazo", "hitos_evaluados"],
        "formula": "hitos_en_plazo / hitos_evaluados * 100",
        "unit": "%",
        "target": Decimal(100),
        "direction": "higher",
        "thresholds": {"green": 90, "yellow": 70},
    },
    {
        "code": "DESV-COSTO",
        "name": "Desviación de costos",
        "objective": "Muestra la diferencia entre valor ganado y costo real.",
        "variables": ["variacion_costo"],
        "formula": "variacion_costo",
        "unit": "CLP",
        "target": Decimal(0),
        "direction": "higher",
        "thresholds": {"green": 0, "yellow": -1},
    },
    {
        "code": "TAREAS-ATRASADAS",
        "name": "Actividades atrasadas",
        "objective": "Cuenta actividades vencidas sin completar.",
        "variables": ["tareas_atrasadas"],
        "formula": "tareas_atrasadas",
        "unit": "actividades",
        "target": Decimal(0),
        "direction": "lower",
        "thresholds": {"green": 0, "yellow": 2},
    },
    {
        "code": "UTIL-PROF",
        "name": "Utilización de profesionales",
        "objective": "Compara horas asignadas con horas disponibles.",
        "variables": ["horas_asignadas", "horas_disponibles"],
        "formula": "horas_asignadas / horas_disponibles * 100",
        "unit": "%",
        "target": Decimal(100),
        "direction": "lower",
        "thresholds": {"green": 100, "yellow": 110},
    },
    {
        "code": "CUMPL-TAREAS",
        "name": "Cumplimiento de actividades",
        "objective": "Mide el porcentaje de actividades completadas.",
        "variables": ["tareas_cumplidas", "tareas_evaluadas"],
        "formula": "tareas_cumplidas / tareas_evaluadas * 100",
        "unit": "%",
        "target": Decimal(100),
        "direction": "higher",
        "thresholds": {"green": 90, "yellow": 70},
    },
    {
        "code": "SPI",
        "name": "Índice de desempeño del cronograma",
        "objective": "Compara el valor ganado con el valor planificado.",
        "variables": ["spi"],
        "formula": "spi",
        "unit": "índice",
        "target": Decimal(1),
        "direction": "higher",
        "thresholds": {"green": 1, "yellow": 0.9},
    },
    {
        "code": "CPI",
        "name": "Índice de desempeño del costo",
        "objective": "Compara el valor ganado con el costo real.",
        "variables": ["cpi"],
        "formula": "cpi",
        "unit": "índice",
        "target": Decimal(1),
        "direction": "higher",
        "thresholds": {"green": 1, "yellow": 0.9},
    },
)


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
    completed_tasks = Decimal(sum(1 for task in tasks if task.progress_percent >= 100))
    earned = _earned_values(session, tasks, planned_cost, actual_cost)
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
        "hitos_evaluados": on_time + overdue_milestones,
        "tareas_cumplidas": completed_tasks,
        **earned,
    }


def _earned_values(
    session: Session,
    tasks: list[Task],
    planned_cost: Decimal,
    actual_cost: Decimal,
) -> dict[str, Decimal]:
    """Calcula PV, EV, AC y los índices de valor ganado con Decimal."""
    today = date.today()
    planned_value = Decimal(0)
    earned_value = Decimal(0)
    for task in tasks:
        cost = task_cost(session, task.id).planned
        if task.planned_start and task.planned_end and task.planned_end >= task.planned_start:
            total_days = Decimal((task.planned_end - task.planned_start).days + 1)
            elapsed_days = Decimal(
                min(max((today - task.planned_start).days + 1, 0), int(total_days))
            )
            planned_value += cost * elapsed_days / total_days
        earned_value += cost * Decimal(str(task.progress_percent)) / Decimal(100)
    spi = earned_value / planned_value if planned_value else Decimal(0)
    cpi = earned_value / actual_cost if actual_cost else Decimal(0)
    return {
        "valor_planificado": planned_value.quantize(Decimal("0.01")),
        "valor_ganado": earned_value.quantize(Decimal("0.01")),
        "variacion_costo": (earned_value - actual_cost).quantize(Decimal("0.01")),
        "variacion_plazo": (earned_value - planned_value).quantize(Decimal("0.01")),
        "costo_estimado_terminar": (
            planned_cost / cpi if cpi > 0 else Decimal(0)
        ).quantize(Decimal("0.01")),
        "spi": spi.quantize(Decimal("0.0001")),
        "cpi": cpi.quantize(Decimal("0.0001")),
    }


def ensure_standard_project_kpis(session: Session, project_id: str) -> None:
    """Crea los ocho KPI estándar si todavía no existen en el proyecto."""
    existing = {
        code
        for code in session.scalars(
            select(KpiDefinition.code).where(KpiDefinition.project_id == project_id)
        )
    }
    for definition in STANDARD_PROJECT_KPIS:
        if definition["code"] in existing:
            continue
        session.add(
            KpiDefinition(
                project_id=project_id,
                scope="project",
                periodicity="automatic",
                source="automatic",
                status="pending",
                **definition,
            )
        )


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
        denominators = {
            "trabajo_total",
            "hitos_evaluados",
            "tareas_evaluadas",
            "horas_disponibles",
        }
        if any(values.get(name) == 0 for name in denominators.intersection(kpi.variables or [])):
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
    ensure_standard_project_kpis(session, project_id)
    session.flush()
    _refresh_automatic_kpis(session, project_id, values)
    return ProjectState(
        progress_percent=progress,
        planned_cost=planned_cost,
        actual_cost=actual_cost,
        overallocated_professionals=professional_overallocations(session, project_id),
        earned_value={
            name: values[name]
            for name in (
                "valor_planificado",
                "valor_ganado",
                "variacion_costo",
                "variacion_plazo",
                "costo_estimado_terminar",
                "spi",
                "cpi",
            )
        },
    )
