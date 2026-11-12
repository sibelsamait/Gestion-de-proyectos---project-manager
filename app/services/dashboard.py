"""Consultas agregadas para Gantt y tableros."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ChangeRequest,
    KpiDefinition,
    KpiMeasurement,
    Milestone,
    Project,
    Resource,
    Task,
    TaskDependency,
    TaskResourceAssignment,
)
from .costs import (
    costs_by_category_for_tasks,
    professional_overallocations,
    project_costs,
    task_cost,
)
from .currency import convert_with_context, currency_context
from .project_state import _earned_values


def _iso(value: date | None) -> str | None:
    """Serializa fechas civiles."""
    return value.isoformat() if value else None


def kpi_measurement_count(session: Session, kpi_id: str) -> int:
    """Cuenta mediciones para verificar que un recálculo dejó historial."""
    return session.scalar(
        select(func.count(KpiMeasurement.id)).where(KpiMeasurement.kpi_id == kpi_id)
    ) or 0


def _filtered_tasks(
    session: Session,
    project_id: str,
    stage: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    responsible_id: str | None = None,
) -> list[Task]:
    """Obtiene tareas que cumplen los filtros visibles del Tablero 1."""
    query = select(Task).where(Task.project_id == project_id)
    if stage:
        query = query.where(Task.etapa == stage)
    if responsible_id:
        query = query.where(Task.responsible_id == responsible_id)
    if date_from:
        query = query.where(Task.planned_end >= date_from)
    if date_to:
        query = query.where(Task.planned_start <= date_to)
    return session.scalars(query.order_by(Task.planned_start, Task.name)).all()


def gantt_data(
    session: Session,
    project_id: str,
    currency: str = "CLP",
    scale: str = "day",
    stage: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    responsible_id: str | None = None,
) -> dict:
    """Construye la representación JSON completa del Gantt."""
    if scale not in {"day", "week", "month"}:
        raise ValueError("La escala debe ser day, week o month.")
    tasks = _filtered_tasks(session, project_id, stage, date_from, date_to, responsible_id)
    dependencies = session.scalars(
        select(TaskDependency)
        .join(Task, Task.id == TaskDependency.predecessor_id)
        .where(Task.project_id == project_id)
    ).all()
    milestones = session.scalars(
        select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.committed_date)
    ).all()
    today = date.today()
    return {
        **currency_context(currency, session=session),
        "scale": scale,
        "filters": {
            "stage": stage,
            "date_from": _iso(date_from),
            "date_to": _iso(date_to),
            "responsible_id": responsible_id,
        },
        "tasks": [
            {
                "id": task.id,
                "name": task.name,
                "etapa": task.etapa,
                "planned_start": _iso(task.planned_start),
                "planned_end": _iso(task.planned_end),
                "actual_start": _iso(task.actual_start),
                "actual_end": _iso(task.actual_end),
                "progress": str(task.progress_percent),
                "overdue": bool(task.planned_end and task.planned_end < today and task.progress_percent < 100),
            }
            for task in tasks
        ],
        "dependencies": [
            {
                "predecessor_id": dependency.predecessor_id,
                "successor_id": dependency.successor_id,
                "type": dependency.dependency_type,
                "lag_days": dependency.lag_days,
            }
            for dependency in dependencies
        ],
        "milestones": [
            {
                "id": milestone.id,
                "name": milestone.name,
                "date": _iso(milestone.committed_date),
                "actual_date": _iso(milestone.actual_date),
                "status": milestone.status,
            }
            for milestone in milestones
        ],
    }


def tracking_dashboard(
    session: Session,
    project: Project,
    currency: str = "CLP",
    stage: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    responsible_id: str | None = None,
) -> dict:
    """Calcula métricas del tablero de seguimiento."""
    tasks = _filtered_tasks(session, project.id, stage, date_from, date_to, responsible_id)
    milestones = session.scalars(select(Milestone).where(Milestone.project_id == project.id)).all()
    evaluated = [task for task in tasks if task.planned_end]
    overdue = [task for task in evaluated if task.planned_end < date.today() and task.progress_percent < 100]
    costs = costs_by_category_for_tasks(session, tasks)
    money = currency_context(currency, session=session)
    planned_cost = sum(costs.values(), Decimal(0))
    actual_cost = sum(
        (task_cost(session, task.id).actual for task in tasks),
        Decimal(0),
    )
    earned = _earned_values(session, tasks, planned_cost, actual_cost)
    kpis = session.scalars(
        select(KpiDefinition).where(
            KpiDefinition.project_id == project.id,
            KpiDefinition.scope == "project",
        )
    ).all()
    professional_ids = {
        resource.id
        for resource in session.scalars(select(Resource).where(Resource.project_id == project.id))
        if resource.type == "Profesional"
    }
    assigned_hours = Decimal(0)
    if professional_ids:
        assigned_hours = session.scalar(
            select(func.coalesce(func.sum(Resource.hours_per_week * TaskResourceAssignment.planned_units), 0))
            .join(TaskResourceAssignment, TaskResourceAssignment.resource_id == Resource.id)
            .where(Resource.id.in_(professional_ids))
        ) or Decimal(0)
    available_hours = session.scalar(
        select(func.coalesce(func.sum(Resource.hours_per_week), 0))
        .where(Resource.project_id == project.id, Resource.type == "Profesional")
    ) or Decimal(0)
    return {
        "project": {"id": project.id, "code": project.code, "name": project.name},
        "filters": {
            "stage": stage,
            "date_from": _iso(date_from),
            "date_to": _iso(date_to),
            "responsible_id": responsible_id,
        },
        "progress": (
            sum((float(task.progress_percent) for task in tasks), 0.0) / len(tasks)
            if tasks
            else 0
        ),
        "task_counts": {"total": len(tasks), "evaluated": len(evaluated), "overdue": len(overdue)},
        "schedule": {
            "planned_duration_days": sum(task.planned_duration_days for task in tasks),
            "planned_start": _iso(min((task.planned_start for task in tasks if task.planned_start), default=None)),
            "planned_end": _iso(max((task.planned_end for task in tasks if task.planned_end), default=None)),
        },
        "milestones": {
            "on_time": sum(1 for milestone in milestones if milestone.status == "cumplido"),
            "overdue": sum(1 for milestone in milestones if milestone.status == "vencido"),
        },
        "costs_by_category": {
            key: str(convert_with_context(value, money)) for key, value in costs.items()
        },
        "professional_utilization": {
            "assigned_hours": str(assigned_hours),
            "available_hours": str(available_hours),
            "percent": float(assigned_hours / available_hours * 100) if available_hours else 0,
            "overallocated": bool(professional_overallocations(session, project.id)),
        },
        "earned_value": {key: str(value) for key, value in earned.items()},
        "kpis": [
            {
                "code": kpi.code,
                "name": kpi.name,
                "result": str(kpi.result) if kpi.result is not None else None,
                "status": kpi.status,
                "measurement_count": kpi_measurement_count(session, kpi.id),
            }
            for kpi in kpis
        ],
        "overdue_tasks": [{"id": task.id, "name": task.name} for task in overdue],
        "tasks": [
            {
                "id": task.id,
                "name": task.name,
                "etapa": task.etapa,
                "responsible_id": task.responsible_id,
                "planned_start": _iso(task.planned_start),
                "planned_end": _iso(task.planned_end),
                "progress": str(task.progress_percent),
            }
            for task in tasks
        ],
        **money,
    }


def change_dashboard(
    session: Session,
    project_id: str,
    currency: str = "CLP",
    status: str | None = None,
    priority: str | None = None,
    change_type: str | None = None,
    responsible_id: str | None = None,
) -> dict:
    """Agrega distribución, riesgos, costos y atrasos de cambios."""
    query = select(ChangeRequest).where(ChangeRequest.project_id == project_id)
    if status:
        query = query.where(ChangeRequest.status == status)
    if priority:
        query = query.where(ChangeRequest.priority == priority)
    if change_type:
        query = query.where(ChangeRequest.change_type == change_type)
    if responsible_id:
        query = query.where(ChangeRequest.responsible_id == responsible_id)
    changes = session.scalars(query).all()
    project = session.get(Project, project_id)
    tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
    project_cost = project_costs(session, project_id)
    earned = _earned_values(session, tasks, sum(project_cost.values(), Decimal(0)), sum(
        (task_cost(session, task.id).actual for task in tasks), Decimal(0)
    ))
    by_status: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for change in changes:
        by_status[change.status] = by_status.get(change.status, 0) + 1
        by_risk[change.risk] = by_risk.get(change.risk, 0) + 1
    today = date.today()
    overdue = [
        change.change_code
        for change in changes
        if change.committed_date and change.committed_date < today and change.actual_date is None
    ]
    implementation_days = [
        (change.actual_date - change.requested_at).days
        for change in changes
        if change.actual_date and change.requested_at
    ]
    corrective_actions = [
        {"code": change.change_code, "action": change.result}
        for change in changes
        if change.result
    ]
    completed_changes = [change for change in changes if change.actual_date]
    effective_changes = [
        change
        for change in completed_changes
        if change.result and change.evidence
    ]
    adoption_score = next(
        (
            kpi.result
            for kpi in session.scalars(
                select(KpiDefinition).where(
                    KpiDefinition.project_id == project_id,
                    KpiDefinition.code == "CHG-ADOPCION",
                )
            )
            if kpi.result is not None
        ),
        Decimal(0),
    )
    change_kpis = session.scalars(
        select(KpiDefinition).where(
            KpiDefinition.project_id == project_id,
            KpiDefinition.scope == "change",
        )
    ).all()
    money = currency_context(currency, session=session)
    return {
        "total": len(changes),
        "changes": [
            {
                "id": change.id,
                "code": change.change_code,
                "status": change.status,
                "stage": change.stage,
                "priority": change.priority,
            }
            for change in changes
        ],
        "by_status": by_status,
        "by_risk": by_risk,
        "estimated_cost": str(
            convert_with_context(sum((change.estimated_cost for change in changes), Decimal(0)), money)
        ),
        "actual_cost": str(
            convert_with_context(sum((change.actual_cost for change in changes), Decimal(0)), money)
        ),
        "overdue": overdue,
        "critical_risks": [change.change_code for change in changes if change.risk == "critico"],
        "stage_completion": {
            stage: sum(1 for change in changes if change.stage == stage)
            for stage in (
                "Registro",
                "Clasificación",
                "Evaluación de impacto",
                "Análisis de riesgo",
                "Decisión",
                "Implementación",
                "Verificación",
                "Cierre con resultado",
                "Seguimiento de adopción",
            )
        },
        "filters": {
            "status": status,
            "priority": priority,
            "type": change_type,
            "responsible_id": responsible_id,
        },
        "kpis": [
            {
                "code": kpi.code,
                "name": kpi.name,
                "result": str(kpi.result) if kpi.result is not None else None,
                "status": kpi.status,
                "measurement_count": kpi_measurement_count(session, kpi.id),
            }
            for kpi in change_kpis
        ],
        "implementation": {
            "average_days": (
                str(
                    Decimal(sum(implementation_days))
                    / Decimal(len(implementation_days))
                )
                if implementation_days
                else "0"
            ),
            "completed": len(completed_changes),
        },
        "corrective_actions": corrective_actions,
        "effectiveness": {
            "percent": (
                str(
                    Decimal(len(effective_changes))
                    / Decimal(len(completed_changes))
                    * 100
                )
                if completed_changes
                else "0"
            ),
            "completed": len(completed_changes),
        },
        "adoption": {"score": str(adoption_score), "scale": "1-5"},
        "alerts": {
            "overdue": overdue,
            "critical_risks": [change.change_code for change in changes if change.risk == "critico"],
            "unmet_kpis": [kpi.code for kpi in change_kpis if kpi.status == "red"],
        },
        "project_state": {
            "progress": str(project.progress_percent),
            "planned_cost": str(sum(project_cost.values(), Decimal(0))),
            "spi": str(earned["spi"]),
            "cpi": str(earned["cpi"]),
            "planned_duration_days": sum(task.planned_duration_days for task in tasks),
        },
        **money,
    }
