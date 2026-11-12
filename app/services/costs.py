"""Cálculo de costos y utilización de profesionales."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ChangeApplication,
    NonWorkingDay,
    Resource,
    Task,
    TaskResourceAssignment,
)

ZERO = Decimal(0)


@dataclass(frozen=True)
class CostBreakdown:
    """Costos calculados para una tarea."""

    planned: Decimal
    actual: Decimal


def activity_weeks(task: Task, holidays: set[date], actual: bool = False) -> Decimal:
    """Calcula semanas hábiles sin redondear resultados intermedios."""
    if actual and task.actual_duration_days > 0:
        if task.actual_start and task.actual_end:
            days = len(_task_workdays(task.actual_start, task.actual_end, holidays))
        else:
            days = task.actual_duration_days
    elif task.planned_start and task.planned_end:
        days = len(_task_workdays(task.planned_start, task.planned_end, holidays))
    else:
        days = task.planned_duration_days
    return Decimal(days) / Decimal(5)


def _resource_cost(
    resource: Resource,
    units: Decimal,
    task: Task,
    holidays: set[date],
    actual: bool = False,
) -> Decimal:
    """Aplica la fórmula de costo según el tipo de recurso."""
    if resource.type == "Profesional":
        weeks = activity_weeks(task, holidays, actual)
        base = resource.hours_per_week * weeks * resource.hourly_rate
    else:
        base = resource.quantity * resource.unit_cost
    return base * units


def task_cost(session: Session, task_id: str) -> CostBreakdown:
    """Calcula costo planificado y real sumando asignaciones."""
    task = session.get(Task, task_id)
    if task is None:
        return CostBreakdown(planned=ZERO, actual=ZERO)
    holidays = set(
        session.scalars(select(NonWorkingDay.day).where(NonWorkingDay.project_id == task.project_id))
    )
    rows = session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(TaskResourceAssignment.task_id == task_id)
    )
    planned = ZERO
    actual = ZERO
    for assignment, resource in rows:
        planned += _resource_cost(resource, assignment.planned_units, task, holidays)
        actual += _resource_cost(resource, assignment.actual_units, task, holidays, actual=True)
    return CostBreakdown(planned=planned.quantize(Decimal("0.01")), actual=actual.quantize(Decimal("0.01")))


def project_costs(session: Session, project_id: str) -> dict[str, Decimal]:
    """Devuelve costos agregados por tipo de recurso."""
    rows = session.execute(
        select(TaskResourceAssignment, Resource, Task)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .join(Task, Task.id == TaskResourceAssignment.task_id)
        .where(Resource.project_id == project_id)
    )
    holidays = set(
        session.scalars(select(NonWorkingDay.day).where(NonWorkingDay.project_id == project_id))
    )
    totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for assignment, resource, task in rows:
        totals[resource.type] += _resource_cost(
            resource, assignment.planned_units, task, holidays
        )
    totals["Cambios"] += project_cost_adjustments(session, project_id)
    return {key: value.quantize(Decimal("0.01")) for key, value in totals.items()}


def costs_by_category_for_tasks(session: Session, tasks: list[Task]) -> dict[str, Decimal]:
    """Calcula costos por categoría para el subconjunto filtrado de tareas."""
    if not tasks:
        return {}
    task_map = {task.id: task for task in tasks}
    holidays = set(
        session.scalars(
            select(NonWorkingDay.day).where(NonWorkingDay.project_id == tasks[0].project_id)
        )
    )
    rows = session.execute(
        select(TaskResourceAssignment, Resource, Task)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .join(Task, Task.id == TaskResourceAssignment.task_id)
        .where(Task.id.in_(task_map))
    )
    totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for assignment, resource, task in rows:
        totals[resource.type] += _resource_cost(
            resource, assignment.planned_units, task, holidays
        )
    return {key: value.quantize(Decimal("0.01")) for key, value in totals.items()}


def project_cost_adjustments(session: Session, project_id: str) -> Decimal:
    """Suma costos adicionales aprobados y trazables."""
    return sum(
        (
            Decimal(value)
            for value in session.scalars(
                select(ChangeApplication.new_value).where(
                    ChangeApplication.entity_type == "project_cost",
                    ChangeApplication.entity_id == project_id,
                    ChangeApplication.attribute == "planned_cost_adjustment",
                )
            )
        ),
        ZERO,
    ).quantize(Decimal("0.01"))


def professional_overallocations(session: Session, project_id: str) -> dict[str, Decimal]:
    """Detecta sobreasignación semanal, manteniendo la salida histórica."""
    details = professional_overallocation_details(session, project_id)
    return {
        resource_id: values["weekly"]
        for resource_id, values in details.items()
        if values["weekly"] > ZERO
    }


def professional_overallocation_details(
    session: Session, project_id: str
) -> dict[str, dict[str, Decimal | dict[str, Decimal]]]:
    """Calcula exceso semanal y diario considerando solapamiento real.

    Las tareas sin fechas conservan el cálculo semanal anterior y no inventan
    una fecha para generar una alerta diaria.
    """
    rows = session.execute(
        select(Resource, TaskResourceAssignment, Task)
        .join(TaskResourceAssignment, TaskResourceAssignment.resource_id == Resource.id)
        .join(Task, Task.id == TaskResourceAssignment.task_id)
        .where(Resource.project_id == project_id, Resource.type == "Profesional")
    )
    weekly: defaultdict[str, defaultdict[object, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    daily: defaultdict[str, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: ZERO)
    )
    holidays = {
        day
        for day in session.scalars(
            select(NonWorkingDay.day).where(NonWorkingDay.project_id == project_id)
        )
    }
    resources: dict[str, Resource] = {}
    for resource, assignment, task in rows:
        resources[resource.id] = resource
        units = assignment.planned_units if assignment.planned_units > ZERO else Decimal(1)
        if not task.planned_start or not task.planned_end:
            weekly[resource.id]["undated"] += resource.hours_per_week * units
            continue
        workdays = _task_workdays(task.planned_start, task.planned_end, holidays)
        if not workdays:
            continue
        hours_per_day = resource.hours_per_week * units / Decimal(5)
        for day in workdays:
            daily[resource.id][day.isoformat()] += hours_per_day
    for resource_id, hours_by_day in daily.items():
        for day, hours in hours_by_day.items():
            weekly[resource_id][date.fromisoformat(day).isocalendar()[:2]] += hours
    result: dict[str, dict[str, Decimal | dict[str, Decimal]]] = {}
    for resource_id, resource in resources.items():
        weekly_excess = max(
            (
                hours - resource.hours_per_week
                for hours in weekly[resource_id].values()
            ),
            default=ZERO,
        )
        daily_excess = {
            day: (hours - resource.daily_max_hours).quantize(Decimal("0.01"))
            for day, hours in daily[resource_id].items()
            if hours > resource.daily_max_hours
        }
        if weekly_excess > ZERO or daily_excess:
            result[resource_id] = {
                "weekly": weekly_excess.quantize(Decimal("0.01")),
                "daily": daily_excess,
            }
    return result


def _task_workdays(start: date, end: date, holidays: set[date]) -> list[date]:
    """Devuelve días hábiles inclusivos del intervalo de una tarea."""
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days
