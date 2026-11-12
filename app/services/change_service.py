"""Aplicación transaccional y trazable de solicitudes de cambio."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ChangeApplication,
    ChangeBaseline,
    ChangeRequest,
    ChangeStageHistory,
    Project,
    Resource,
    Task,
    TaskResourceAssignment,
)
from .costs import activity_weeks
from .project_state import recalculate_project_state
from .scheduler import add_working_days, working_days


class ChangeError(ValueError):
    """Error de flujo o impacto de cambio."""


STAGES = (
    "Registro",
    "Clasificación",
    "Evaluación de impacto",
    "Análisis de riesgo",
    "Decisión",
    "Planificación de la implementación",
    "Implementación",
    "Verificación",
    "Cierre con resultado",
    "Seguimiento de adopción",
)


def capture_baseline(session: Session, change: ChangeRequest) -> ChangeBaseline:
    """Captura presupuesto y fechas de tareas antes de aplicar el cambio."""
    project = session.get(Project, change.project_id)
    tasks = session.scalars(select(Task).where(Task.project_id == change.project_id)).all()
    snapshot = {
        "project": {
            "authorized_budget": str(project.authorized_budget),
            "planned_start": project.planned_start.isoformat() if project.planned_start else None,
            "planned_end": project.planned_end.isoformat() if project.planned_end else None,
        },
        "tasks": {
            task.id: {
                "planned_start": task.planned_start.isoformat() if task.planned_start else None,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
            }
            for task in tasks
        },
    }
    baseline = ChangeBaseline(change_request_id=change.id, snapshot=snapshot)
    session.add(baseline)
    return baseline


def transition_change(
    session: Session,
    change: ChangeRequest,
    actor_id: str,
    comment: str,
) -> ChangeStageHistory:
    """Avanza exactamente una etapa y registra quién, cuándo y por qué."""
    try:
        current_index = STAGES.index(change.stage)
    except ValueError as exc:
        raise ChangeError("La solicitud tiene una etapa inválida.") from exc
    if current_index >= len(STAGES) - 1:
        raise ChangeError("La solicitud ya está en la última etapa.")
    comment = comment.strip()
    if not comment:
        raise ChangeError("Debes explicar brevemente el avance.")
    previous_stage = change.stage
    change.stage = STAGES[current_index + 1]
    change.status = "in_progress"
    change.version += 1
    history = ChangeStageHistory(
        change_request_id=change.id,
        from_stage=previous_stage,
        to_stage=change.stage,
        actor_id=actor_id,
        comment=comment,
    )
    session.add(history)
    return history


def approve_change(session: Session, change: ChangeRequest, approver_role: str) -> list[ChangeApplication]:
    """Aprueba y aplica impactos declarados dentro de la transacción."""
    if approver_role not in {"admin", "director"}:
        raise ChangeError("El rol no está autorizado para aprobar cambios.")
    if change.status == "approved":
        raise ChangeError("La solicitud ya fue aprobada.")
    if change.stage != "Decisión":
        raise ChangeError("La solicitud debe estar en la etapa Decisión.")
    if not change.impact:
        raise ChangeError("El cambio debe declarar su impacto.")
    capture_baseline(session, change)
    applications: list[ChangeApplication] = []
    project = session.get(Project, change.project_id)
    structured_cost = "additional_cost" in change.impact
    budget_delta = Decimal(str(change.impact.get("additional_cost", change.impact.get("budget_delta", "0"))))
    if structured_cost and budget_delta < 0:
        raise ChangeError("El costo adicional no puede ser negativo.")
    if budget_delta:
        old = project.authorized_budget
        project.authorized_budget = old + budget_delta
        if project.authorized_budget < 0:
            raise ChangeError("El Presupuesto resultante no puede ser negativo.")
        applications.append(
            ChangeApplication(
                change_request_id=change.id,
                entity_type="project",
                entity_id=project.id,
                attribute="authorized_budget",
                old_value=str(old),
                new_value=str(project.authorized_budget),
            )
        )
        if structured_cost:
            applications.append(
                ChangeApplication(
                    change_request_id=change.id,
                    entity_type="project_cost",
                    entity_id=project.id,
                    attribute="planned_cost_adjustment",
                    old_value="0",
                    new_value=str(budget_delta),
                )
            )
    schedule = change.impact.get("additional_days")
    if schedule:
        if not isinstance(schedule, dict):
            raise ChangeError("Los días adicionales deben indicar actividad y cantidad.")
        _apply_schedule_impact(session, change, schedule, applications)
    for update in change.impact.get("tasks", []):
        task = session.scalar(
            select(Task).where(Task.id == update.get("task_id"), Task.project_id == change.project_id)
        )
        if task is None or update.get("planned_end") is None:
            raise ChangeError("El impacto referencia una tarea o fecha inválida.")
        new_end = date.fromisoformat(update["planned_end"])
        old_end = task.planned_end
        task.planned_end = new_end
        applications.append(
            ChangeApplication(
                change_request_id=change.id,
                entity_type="task",
                entity_id=task.id,
                attribute="planned_end",
                old_value=old_end.isoformat() if old_end else "null",
                new_value=new_end.isoformat(),
            )
        )
    resource_impact = change.impact.get("additional_resource")
    if resource_impact:
        if not isinstance(resource_impact, dict):
            raise ChangeError("El recurso adicional debe indicar actividad y recurso.")
        _apply_resource_impact(session, change, resource_impact, applications)
    session.add_all(applications)
    change.status = "approved"
    change.stage = "Planificación de la implementación"
    change.version += 1
    recalculate_project_state(session, change.project_id)
    return applications


def _apply_schedule_impact(
    session: Session,
    change: ChangeRequest,
    impact: dict,
    applications: list[ChangeApplication],
) -> None:
    """Aplica días adicionales sobre una actividad del mismo proyecto."""
    task = session.scalar(
        select(Task).where(
            Task.id == impact.get("task_id"),
            Task.project_id == change.project_id,
        )
    )
    try:
        days = int(impact.get("days", 0))
    except (TypeError, ValueError) as exc:
        raise ChangeError("Los días adicionales deben ser un número entero.") from exc
    if task is None or days < 0 or not task.planned_start or not task.planned_end:
        raise ChangeError("La actividad o sus fechas no permiten aplicar días adicionales.")
    old_end = task.planned_end
    new_end = add_working_days(
        old_end,
        days,
        working_days(change.project_id, session),
    )
    task.planned_duration_days += days
    task.planned_end = new_end
    applications.append(
        ChangeApplication(
            change_request_id=change.id,
            entity_type="task",
            entity_id=task.id,
            attribute="planned_duration_days",
            old_value=str(task.planned_duration_days - days),
            new_value=str(task.planned_duration_days),
        )
    )
    applications.append(
        ChangeApplication(
            change_request_id=change.id,
            entity_type="task",
            entity_id=task.id,
            attribute="planned_end",
            old_value=old_end.isoformat(),
            new_value=new_end.isoformat(),
        )
    )


def _apply_resource_impact(
    session: Session,
    change: ChangeRequest,
    impact: dict,
    applications: list[ChangeApplication],
) -> None:
    """Agrega horas/unidades de un recurso a una actividad."""
    task = session.scalar(
        select(Task).where(Task.id == impact.get("task_id"), Task.project_id == change.project_id)
    )
    resource = session.scalar(
        select(Resource).where(
            Resource.id == impact.get("resource_id"),
            Resource.project_id == change.project_id,
        )
    )
    if task is None or resource is None:
        raise ChangeError("La actividad o el recurso adicional no pertenece al proyecto.")
    try:
        hours = Decimal(str(impact.get("hours", "0")))
    except (ArithmeticError, ValueError) as exc:
        raise ChangeError("Las horas adicionales no son válidas.") from exc
    if hours < 0:
        raise ChangeError("Las horas adicionales no pueden ser negativas.")
    if hours:
        holidays = working_days(change.project_id, session)
        divisor = resource.hours_per_week * activity_weeks(task, holidays)
        if resource.type == "Profesional" and divisor <= 0:
            raise ChangeError("El profesional no tiene una capacidad semanal válida.")
        units = hours / divisor if resource.type == "Profesional" else hours
    else:
        units = Decimal(str(impact.get("units", "0")))
    if units <= 0:
        raise ChangeError("Debes indicar horas o unidades adicionales mayores que cero.")
    assignment = session.scalar(
        select(TaskResourceAssignment).where(
            TaskResourceAssignment.task_id == task.id,
            TaskResourceAssignment.resource_id == resource.id,
        )
    )
    old_units = assignment.planned_units if assignment else Decimal(0)
    if assignment is None:
        assignment = TaskResourceAssignment(
            task_id=task.id, resource_id=resource.id, planned_units=0, actual_units=0
        )
        session.add(assignment)
    assignment.planned_units = old_units + units
    applications.append(
        ChangeApplication(
            change_request_id=change.id,
            entity_type="task_resource_assignment",
            entity_id=task.id,
            attribute=f"planned_units:{resource.id}",
            old_value=str(old_units),
            new_value=str(assignment.planned_units),
        )
    )
