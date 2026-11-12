"""CRUD de proyectos, tareas, recursos e hitos."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from ...extensions import db
from ...models import (
    Milestone,
    Project,
    ProjectMembership,
    Resource,
    Task,
    TaskDependency,
)
from ...services.audit import record_audit
from ...services.project_state import recalculate_project_state
from ...services.scheduler import validate_dependency
from ..projects import project_access_required

work_bp = Blueprint("work", __name__, url_prefix="/projects")


def _date(value: str | None) -> date | None:
    """Convierte una fecha ISO o devuelve None para campos vacíos."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("La fecha debe usar el formato AAAA-MM-DD.") from exc


def _decimal(value: str | None, field: str) -> Decimal:
    """Convierte dinero/cantidades sin usar float."""
    try:
        number = Decimal(value or "0")
    except InvalidOperation as exc:
        raise ValueError(f"{field} debe ser un número válido.") from exc
    if number < 0:
        raise ValueError(f"{field} no puede ser negativo.")
    return number


def _text(name: str, maximum: int, required: bool = True) -> str | None:
    value = request.form.get(name, "").strip()
    if required and not value:
        raise ValueError(f"{name} es obligatorio.")
    if len(value) > maximum:
        raise ValueError(f"{name} supera el máximo permitido.")
    return value or None


def _can_manage(project_id: str) -> bool:
    """Permite escritura al administrador o al manager del proyecto."""
    if current_user.is_admin:
        return True
    return db.session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == current_user.id,
            ProjectMembership.membership_role == "manager",
        )
    ) is not None


def _recalculate(project_id: str) -> None:
    """Ejecuta el único recálculo antes de confirmar cambios del proyecto."""
    recalculate_project_state(db.session, project_id)


@work_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_project() -> str:
    """Crea un proyecto; solo administradores pueden crear portafolio."""
    if not current_user.is_admin:
        abort(403)
    if request.method == "POST":
        try:
            project = Project(
                code=_text("code", 40).upper(),
                name=_text("name", 160),
                description=_text("description", 5000, False),
                objectives=_text("objectives", 5000, False),
                sponsor=_text("sponsor", 160, False),
                authorized_budget=_decimal(request.form.get("authorized_budget"), "presupuesto"),
                planned_start=_date(request.form.get("planned_start")),
                planned_end=_date(request.form.get("planned_end")),
                director_id=current_user.id,
            )
            if project.planned_start and project.planned_end and project.planned_end < project.planned_start:
                raise ValueError("La fecha de término no puede preceder al inicio.")
            if db.session.scalar(select(Project).where(Project.code == project.code)):
                raise ValueError("El código del proyecto ya existe.")
            db.session.add(project)
            db.session.flush()
            db.session.add(ProjectMembership(project_id=project.id, user_id=current_user.id, membership_role="manager"))
            _recalculate(project.id)
            record_audit("project.created", "project", project.id)
            db.session.commit()
            flash("Proyecto creado.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except (ValueError, KeyError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/project_form.html", project=None)


@work_bp.route("/<string:project_id>/edit", methods=["GET", "POST"])
@project_access_required
def edit_project(project: Project) -> str:
    """Edita datos básicos de un proyecto autorizado."""
    if not _can_manage(project.id):
        abort(403)
    if request.method == "POST":
        try:
            project.name = _text("name", 160)
            project.description = _text("description", 5000, False)
            project.objectives = _text("objectives", 5000, False)
            project.sponsor = _text("sponsor", 160, False)
            project.authorized_budget = _decimal(request.form.get("authorized_budget"), "presupuesto")
            project.planned_start = _date(request.form.get("planned_start"))
            project.planned_end = _date(request.form.get("planned_end"))
            project.status = _text("status", 30)
            if project.status not in {"planificado", "en_ejecucion", "suspendido", "terminado"}:
                raise ValueError("Estado de proyecto inválido.")
            if project.planned_start and project.planned_end and project.planned_end < project.planned_start:
                raise ValueError("La fecha de término no puede preceder al inicio.")
            _recalculate(project.id)
            record_audit("project.updated", "project", project.id)
            db.session.commit()
            flash("Proyecto actualizado.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except (ValueError, KeyError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/project_form.html", project=project)


def _project_object(project: Project, kind: str) -> Any:
    """Resuelve el objeto de proyecto para las vistas CRUD."""
    if kind == "task":
        return Task(project_id=project.id)
    if kind == "resource":
        return Resource(project_id=project.id, type="Otros")
    return Milestone(project_id=project.id)


@work_bp.route("/<string:project_id>/<string:kind>/new", methods=["GET", "POST"])
@project_access_required
def create_work_item(project: Project, kind: str) -> str:
    """Crea una tarea, recurso o hito con validación común."""
    if kind not in {"task", "resource", "milestone"}:
        abort(404)
    if not _can_manage(project.id):
        abort(403)
    item = _project_object(project, kind)
    if request.method == "POST":
        try:
            if kind == "task":
                item.name = _text("name", 160)
                item.description = _text("description", 5000, False)
                item.etapa = _text("etapa", 120, False)
                item.planned_start = _date(request.form.get("planned_start"))
                item.planned_end = _date(request.form.get("planned_end"))
                item.planned_duration_days = int(request.form.get("planned_duration_days", 0))
                item.progress_percent = _decimal(request.form.get("progress_percent"), "avance")
                if item.progress_percent > 100 or item.planned_duration_days < 0:
                    raise ValueError("Duración o avance inválido.")
                if item.planned_start and item.planned_end and item.planned_end < item.planned_start:
                    raise ValueError("La fecha de término no puede preceder al inicio.")
            elif kind == "resource":
                item.name = _text("name", 160)
                item.type = _text("type", 30)
                if item.type not in {"Profesional", "Licencia", "Material", "Equipamiento", "Otros"}:
                    raise ValueError("Tipo de recurso inválido.")
                item.specialty = _text("specialty", 120, False)
                item.hourly_rate = _decimal(request.form.get("hourly_rate"), "valor hora")
                item.hours_per_week = _decimal(request.form.get("hours_per_week"), "horas semanales")
                item.quantity = _decimal(request.form.get("quantity"), "cantidad")
                item.unit_cost = _decimal(request.form.get("unit_cost"), "valor unitario")
            else:
                item.name = _text("name", 160)
                item.description = _text("description", 5000, False)
                item.committed_date = _date(request.form.get("committed_date"))
                item.acceptance_criteria = _text("acceptance_criteria", 5000, False)
                item.evidence = _text("evidence", 5000, False)
            db.session.add(item)
            db.session.flush()
            _recalculate(project.id)
            record_audit(f"{kind}.created", kind, item.id)
            db.session.commit()
            flash("Elemento creado.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/work_form.html", project=project, kind=kind, item=item)


@work_bp.route("/<string:project_id>/<string:kind>/<string:item_id>/edit", methods=["GET", "POST"])
@project_access_required
def edit_work_item(project: Project, kind: str, item_id: str) -> str:
    """Actualiza una tarea, recurso o hito perteneciente al proyecto."""
    model = {"task": Task, "resource": Resource, "milestone": Milestone}.get(kind)
    if model is None:
        abort(404)
    if not _can_manage(project.id):
        abort(403)
    item = db.session.scalar(select(model).where(model.id == item_id, model.project_id == project.id))
    if item is None:
        abort(404)
    if request.method == "POST":
        try:
            if kind == "task":
                item.name = _text("name", 160)
                item.description = _text("description", 5000, False)
                item.etapa = _text("etapa", 120, False)
                item.planned_start = _date(request.form.get("planned_start"))
                item.planned_end = _date(request.form.get("planned_end"))
                item.planned_duration_days = int(request.form.get("planned_duration_days", 0))
                item.progress_percent = _decimal(request.form.get("progress_percent"), "avance")
                if item.progress_percent > 100 or item.planned_duration_days < 0:
                    raise ValueError("Duración o avance inválido.")
            elif kind == "resource":
                item.name = _text("name", 160)
                item.type = _text("type", 30)
                if item.type not in {"Profesional", "Licencia", "Material", "Equipamiento", "Otros"}:
                    raise ValueError("Tipo de recurso inválido.")
                item.specialty = _text("specialty", 120, False)
                item.hourly_rate = _decimal(request.form.get("hourly_rate"), "valor hora")
                item.hours_per_week = _decimal(request.form.get("hours_per_week"), "horas semanales")
                item.quantity = _decimal(request.form.get("quantity"), "cantidad")
                item.unit_cost = _decimal(request.form.get("unit_cost"), "valor unitario")
            else:
                item.name = _text("name", 160)
                item.description = _text("description", 5000, False)
                item.committed_date = _date(request.form.get("committed_date"))
                item.acceptance_criteria = _text("acceptance_criteria", 5000, False)
                item.evidence = _text("evidence", 5000, False)
            _recalculate(project.id)
            record_audit(f"{kind}.updated", kind, item.id)
            db.session.commit()
            flash("Elemento actualizado.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except (ValueError, TypeError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/work_form.html", project=project, kind=kind, item=item)


@work_bp.post("/<string:project_id>/tasks/<string:task_id>/dependencies")
@project_access_required
def create_dependency(project: Project, task_id: str) -> tuple[dict[str, str], int]:
    """Crea una dependencia válida dentro del mismo proyecto."""
    if not _can_manage(project.id):
        abort(403)
    predecessor_id = request.form.get("predecessor_id", "")
    dependency_type = request.form.get("dependency_type", "FS")
    try:
        successor = db.session.scalar(
            select(Task).where(Task.id == task_id, Task.project_id == project.id)
        )
        predecessor = db.session.scalar(
            select(Task).where(Task.id == predecessor_id, Task.project_id == project.id)
        )
        if not successor or not predecessor:
            raise ValueError("La tarea no pertenece al proyecto.")
        if successor.id == predecessor.id:
            raise ValueError("Una tarea no puede depender de sí misma.")
        if dependency_type not in {"FS", "SS", "FF", "SF"}:
            raise ValueError("Tipo de dependencia inválido.")
        dependency = TaskDependency(
            predecessor_id=predecessor.id,
            successor_id=successor.id,
            dependency_type=dependency_type,
            lag_days=int(request.form.get("lag_days", "0")),
        )
        validate_dependency(db.session, dependency)
        db.session.add(dependency)
        db.session.flush()
        _recalculate(project.id)
        record_audit("task_dependency.created", "task_dependency", successor.id)
        db.session.commit()
        return {"message": "Dependencia creada."}, 201
    except (ValueError, TypeError) as error:
        db.session.rollback()
        return {"error": str(error)}, 400


@work_bp.post("/<string:project_id>/<string:kind>/<string:item_id>/delete")
@project_access_required
def delete_work_item(project: Project, kind: str, item_id: str) -> tuple[str, int]:
    """Elimina un elemento del proyecto tras comprobar pertenencia."""
    if not _can_manage(project.id):
        abort(403)
    model = {"task": Task, "resource": Resource, "milestone": Milestone}.get(kind)
    if model is None:
        abort(404)
    item = db.session.scalar(select(model).where(model.id == item_id, model.project_id == project.id))
    if item is None:
        abort(404)
    db.session.delete(item)
    db.session.flush()
    _recalculate(project.id)
    record_audit(f"{kind}.deleted", kind, item_id)
    db.session.commit()
    flash("Elemento eliminado.", "success")
    return redirect(url_for("projects.detail", project_id=project.id))
