"""Aplicación transaccional y trazable de solicitudes de cambio."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ChangeApplication,
    ChangeBaseline,
    ChangeRequest,
    Project,
    Task,
)
from .scheduler import recalculate_project


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


def approve_change(session: Session, change: ChangeRequest, approver_role: str) -> list[ChangeApplication]:
    """Aprueba y aplica impactos declarados dentro de la transacción."""
    if approver_role not in {"admin", "manager"}:
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
    budget_delta = Decimal(str(change.impact.get("budget_delta", "0")))
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
    session.add_all(applications)
    recalculate_project(change.project_id, session)
    change.status = "approved"
    change.stage = "Implementación"
    change.version += 1
    return applications
