"""Cálculo de costos y utilización de profesionales."""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Resource, TaskResourceAssignment

ZERO = Decimal(0)


@dataclass(frozen=True)
class CostBreakdown:
    """Costos calculados para una tarea."""

    planned: Decimal
    actual: Decimal


def _resource_cost(resource: Resource, units: Decimal, actual: bool = False) -> Decimal:
    """Aplica la fórmula de costo según el tipo de recurso."""
    if resource.type == "Profesional":
        base = resource.hours_per_week * resource.weeks * resource.hourly_rate
    else:
        base = resource.quantity * resource.unit_cost
    return base * units


def task_cost(session: Session, task_id: str) -> CostBreakdown:
    """Calcula costo planificado y real sumando asignaciones."""
    rows = session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(TaskResourceAssignment.task_id == task_id)
    )
    planned = ZERO
    actual = ZERO
    for assignment, resource in rows:
        planned += _resource_cost(resource, assignment.planned_units)
        actual += _resource_cost(resource, assignment.actual_units, actual=True)
    return CostBreakdown(planned=planned.quantize(Decimal("0.01")), actual=actual.quantize(Decimal("0.01")))


def project_costs(session: Session, project_id: str) -> dict[str, Decimal]:
    """Devuelve costos agregados por tipo de recurso."""
    rows = session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(Resource.project_id == project_id)
    )
    totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for assignment, resource in rows:
        totals[resource.type] += _resource_cost(resource, assignment.planned_units)
    return {key: value.quantize(Decimal("0.01")) for key, value in totals.items()}


def professional_overallocations(session: Session, project_id: str) -> dict[str, Decimal]:
    """Detecta horas semanales asignadas por encima de disponibilidad."""
    rows = session.execute(
        select(Resource, TaskResourceAssignment)
        .join(TaskResourceAssignment, TaskResourceAssignment.resource_id == Resource.id)
        .where(Resource.project_id == project_id, Resource.type == "Profesional")
    )
    assigned: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    available: dict[str, Decimal] = {}
    for resource, assignment in rows:
        assigned[resource.id] += resource.hours_per_week * (
            assignment.planned_units if assignment.planned_units > ZERO else Decimal(1)
        )
        available[resource.id] = resource.hours_per_week
    return {
        resource_id: (assigned[resource_id] - available[resource_id]).quantize(Decimal("0.01"))
        for resource_id in assigned
        if assigned[resource_id] > available[resource_id]
    }
