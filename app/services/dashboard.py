"""Consultas agregadas para Gantt y tableros."""

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
    TaskDependency,
    TaskResourceAssignment,
)
from .costs import professional_overallocations, project_costs


def _iso(value: date | None) -> str | None:
    """Serializa fechas civiles."""
    return value.isoformat() if value else None


def gantt_data(session: Session, project_id: str) -> dict:
    """Construye la representación JSON completa del Gantt."""
    tasks = session.scalars(
        select(Task).where(Task.project_id == project_id).order_by(Task.planned_start, Task.name)
    ).all()
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


def tracking_dashboard(session: Session, project: Project) -> dict:
    """Calcula métricas del tablero de seguimiento."""
    tasks = session.scalars(select(Task).where(Task.project_id == project.id)).all()
    milestones = session.scalars(select(Milestone).where(Milestone.project_id == project.id)).all()
    evaluated = [task for task in tasks if task.planned_end]
    overdue = [task for task in evaluated if task.planned_end < date.today() and task.progress_percent < 100]
    costs = project_costs(session, project.id)
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
        "progress": (
            sum((float(task.progress_percent) for task in tasks), 0.0) / len(tasks)
            if tasks
            else 0
        ),
        "task_counts": {"total": len(tasks), "evaluated": len(evaluated), "overdue": len(overdue)},
        "milestones": {
            "on_time": sum(1 for milestone in milestones if milestone.status == "cumplido"),
            "overdue": sum(1 for milestone in milestones if milestone.status == "vencido"),
        },
        "costs_by_category": {key: str(value) for key, value in costs.items()},
        "professional_utilization": {
            "assigned_hours": str(assigned_hours),
            "available_hours": str(available_hours),
            "percent": float(assigned_hours / available_hours * 100) if available_hours else 0,
            "overallocated": bool(professional_overallocations(session, project.id)),
        },
        "overdue_tasks": [{"id": task.id, "name": task.name} for task in overdue],
    }


def change_dashboard(session: Session, project_id: str) -> dict:
    """Agrega distribución, riesgos, costos y atrasos de cambios."""
    changes = session.scalars(
        select(ChangeRequest).where(ChangeRequest.project_id == project_id)
    ).all()
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
    return {
        "total": len(changes),
        "by_status": by_status,
        "by_risk": by_risk,
        "estimated_cost": str(sum((change.estimated_cost for change in changes), Decimal(0))),
        "actual_cost": str(sum((change.actual_cost for change in changes), Decimal(0))),
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
            )
        },
        "kpis": [
            {"code": kpi.code, "name": kpi.name, "result": str(kpi.result) if kpi.result is not None else None, "status": kpi.status}
            for kpi in session.scalars(select(KpiDefinition).where(KpiDefinition.project_id == project_id, KpiDefinition.scope == "change"))
        ],
    }
