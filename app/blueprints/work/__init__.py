"""Alta, edición y eliminación de proyectos, tareas, recursos, hitos y dependencias."""

from decimal import Decimal
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import select

from ... import validation as v
from ...extensions import db
from ...models import (
    Milestone,
    Project,
    ProjectMember,
    Resource,
    Task,
    TaskDependency,
    TaskResourceAssignment,
)
from ...services.audit import record_audit
from ...services.costs import assignment_cost
from ...services.scheduler import validate_dependency
from ..projects import load_project, require_role

work_bp = Blueprint("work", __name__, url_prefix="/projects")

MODELS = {"task": Task, "resource": Resource, "milestone": Milestone}
MESSAGES = {
    "task": {"created": "Tarea creada.", "updated": "Tarea actualizada.", "deleted": "Tarea eliminada."},
    "resource": {"created": "Recurso creado.", "updated": "Recurso actualizado.", "deleted": "Recurso eliminado."},
    "milestone": {"created": "Hito creado.", "updated": "Hito actualizado.", "deleted": "Hito eliminado."},
}
VERBS = {
    "task": ("Tarea", "creada", "actualizada", "eliminada"),
    "resource": ("Recurso", "creado", "actualizado", "eliminado"),
    "milestone": ("Hito", "creado", "actualizado", "eliminado"),
}


def _describe(kind: str, name: str, action: str) -> str:
    """Descripción legible del cambio, p. ej. «Tarea «Diseño» creada»."""
    noun, created, updated, deleted = VERBS[kind]
    verb = {"created": created, "updated": updated, "deleted": deleted}[action]
    return f"{noun} «{name}» {verb}"
# Recursos definen tarifas y costos (presupuesto): los administra el gerente.
KIND_MIN_ROLE = {"task": "gestor", "milestone": "gestor", "resource": "admin"}
KIND_TABS = {"task": "tareas", "resource": "recursos", "milestone": "hitos"}


def _apply_project_form(project: Project) -> None:
    """Valida y asigna los campos editables de un proyecto."""
    project.name = v.text("name", "El nombre", Project.name, required=True)
    project.description = v.text("description", "La descripción")
    project.objectives = v.text("objectives", "Los objetivos")
    project.sponsor = v.text("sponsor", "El patrocinador", Project.sponsor)
    project.director_id = v.user_ref("director_id", "El director", v.people(project.id))
    project.authorized_budget = v.decimal("authorized_budget", "El presupuesto")
    project.planned_start = v.iso_date("planned_start", "El inicio planificado")
    project.planned_end = v.iso_date("planned_end", "El término planificado")
    project.control_plan = v.text("control_plan", "La estrategia de monitoreo y control")
    v.date_order(project.planned_start, project.planned_end)


def _apply_item_form(item: Any, kind: str) -> None:
    """Valida y asigna los campos de una tarea, recurso o hito."""
    model = MODELS[kind]
    item.name = v.text("name", "El nombre", model.name, required=True)
    if kind == "task":
        item.description = v.text("description", "La descripción")
        item.etapa = v.text("etapa", "La etapa", Task.etapa)
        item.responsible_id = v.user_ref("responsible_id", "El responsable", v.people(item.project_id))
        item.planned_start = v.iso_date("planned_start", "El inicio planificado")
        item.planned_end = v.iso_date("planned_end", "El término planificado")
        item.planned_duration_days = v.integer("planned_duration_days", "La duración")
        item.progress_percent = v.decimal("progress_percent", "El avance", maximum=Decimal(100))
        v.date_order(item.planned_start, item.planned_end)
    elif kind == "resource":
        item.type = v.choice("type", "El tipo de recurso", Resource.type)
        item.specialty = v.text("specialty", "La especialidad", Resource.specialty)
        item.hourly_rate = v.decimal("hourly_rate", "El valor hora")
        item.hours_per_week = v.decimal("hours_per_week", "Las horas semanales")
        item.weeks = v.decimal("weeks", "Las semanas")
        item.quantity = v.decimal("quantity", "La cantidad")
        item.unit_cost = v.decimal("unit_cost", "El valor unitario")
    else:
        item.description = v.text("description", "La descripción")
        item.responsible_id = v.user_ref("responsible_id", "El responsable", v.people(item.project_id))
        item.committed_date = v.iso_date("committed_date", "La fecha comprometida")
        item.actual_date = v.iso_date("actual_date", "La fecha real")
        item.status = v.choice("status", "El estado del hito", Milestone.status, default="pendiente")
        item.acceptance_criteria = v.text("acceptance_criteria", "Los criterios de aceptación")
        item.evidence = v.text("evidence", "La evidencia")


def _assignments(task: Task) -> list[dict]:
    """Recursos asignados a la tarea con su costo planificado y real (CLP)."""
    if task.id is None:
        return []
    rows = db.session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(TaskResourceAssignment.task_id == task.id)
        .order_by(Resource.type, Resource.name)
    ).all()
    return [
        {
            "assignment": assignment,
            "resource": resource,
            "planned_cost": assignment_cost(resource, assignment.planned_units),
            "actual_cost": assignment_cost(resource, assignment.actual_units),
        }
        for assignment, resource in rows
    ]


def _resources(project_id: str) -> list[Resource]:
    return list(
        db.session.scalars(select(Resource).where(Resource.project_id == project_id).order_by(Resource.type, Resource.name))
    )


def _project_item(project: Project, kind: str, item_id: str) -> Any:
    """Obtiene un elemento que pertenezca al proyecto o responde 404."""
    model = MODELS.get(kind)
    if model is None:
        abort(404)
    item = db.session.scalar(select(model).where(model.id == item_id, model.project_id == project.id))
    if item is None:
        abort(404)
    return item


@work_bp.route("/new", methods=["GET", "POST"])
def create_project() -> Any:
    """Crea un proyecto nuevo."""
    if request.method == "POST":
        try:
            code = v.text("code", "El código", Project.code, required=True).upper()
            if db.session.scalar(select(Project).where(Project.code == code)):
                raise ValueError("El código del proyecto ya existe.")
            project = Project(code=code, status="planificado", director_id=g.user.id)
            _apply_project_form(project)
            project.director_id = project.director_id or g.user.id
            db.session.add(project)
            # Quien crea el proyecto queda como su administrador.
            db.session.add(ProjectMember(project=project, email=g.user.email, role="admin"))
            g.project_role = "admin"
            record_audit("project.created", f"Proyecto «{project.name}» creado", project)
            db.session.commit()
            flash("Proyecto creado. Complete tareas, hitos y recursos para preparar el informe.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/project_form.html", project=None, people=v.people())


@work_bp.route("/<string:project_id>/edit", methods=["GET", "POST"])
@load_project
def edit_project(project: Project) -> Any:
    """Edita los datos generales de un proyecto (solo administradores)."""
    require_role("admin")
    if request.method == "POST":
        try:
            _apply_project_form(project)
            project.status = v.choice("status", "El estado del proyecto", Project.status)
            if project.phase == "preinversion" and project.status in ("en_ejecucion", "terminado"):
                raise ValueError(
                    "El proyecto sigue en preinversión: regístrelo como autorizado en la pestaña "
                    "Preinversión antes de iniciar su ejecución."
                )
            record_audit("project.updated", f"Datos del proyecto «{project.name}» actualizados", project)
            db.session.commit()
            flash("Proyecto actualizado.", "success")
            return redirect(url_for("projects.detail", project_id=project.id))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("projects/project_form.html", project=project, people=v.people(project.id))


@work_bp.route("/<string:project_id>/<string:kind>/new", methods=["GET", "POST"])
@load_project
def create_work_item(project: Project, kind: str) -> Any:
    """Crea una tarea o hito (jefe o gerente) o un recurso (solo gerente: define costos)."""
    if kind not in MODELS:
        abort(404)
    require_role(KIND_MIN_ROLE[kind])
    item = MODELS[kind](project_id=project.id)
    if request.method == "POST":
        try:
            _apply_item_form(item, kind)
            db.session.add(item)
            record_audit(f"{kind}.created", _describe(kind, item.name, "created"), project)
            db.session.commit()
            flash(MESSAGES[kind]["created"], "success")
            return redirect(url_for("projects.detail", project_id=project.id, vista=KIND_TABS[kind]))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "projects/work_form.html",
        project=project,
        kind=kind,
        item=item,
        people=v.people(project.id),
        assignments=_assignments(item) if kind == "task" else [],
        resources=_resources(project.id) if kind == "task" else [],
    )


@work_bp.route("/<string:project_id>/<string:kind>/<string:item_id>/edit", methods=["GET", "POST"])
@load_project
def edit_work_item(project: Project, kind: str, item_id: str) -> Any:
    """Actualiza una tarea, recurso o hito del proyecto según el rol requerido."""
    require_role(KIND_MIN_ROLE.get(kind, "gestor"))
    item = _project_item(project, kind, item_id)
    if request.method == "POST":
        try:
            _apply_item_form(item, kind)
            record_audit(f"{kind}.updated", _describe(kind, item.name, "updated"), project)
            db.session.commit()
            flash(MESSAGES[kind]["updated"], "success")
            return redirect(url_for("projects.detail", project_id=project.id, vista=KIND_TABS[kind]))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "projects/work_form.html",
        project=project,
        kind=kind,
        item=item,
        people=v.people(project.id),
        assignments=_assignments(item) if kind == "task" else [],
        resources=_resources(project.id) if kind == "task" else [],
    )


@work_bp.post("/<string:project_id>/tasks/<string:task_id>/dependencies")
@load_project
def create_dependency(project: Project, task_id: str) -> tuple[dict[str, str], int]:
    """Crea una dependencia entre dos tareas del mismo proyecto (gestor o administrador)."""
    require_role("gestor")
    try:
        successor = db.session.scalar(select(Task).where(Task.id == task_id, Task.project_id == project.id))
        predecessor = db.session.scalar(
            select(Task).where(Task.id == request.form.get("predecessor_id", ""), Task.project_id == project.id)
        )
        if not successor or not predecessor:
            raise ValueError("La tarea no pertenece al proyecto.")
        if successor.id == predecessor.id:
            raise ValueError("Una tarea no puede depender de sí misma.")
        lag = request.form.get("lag_days", "0").strip() or "0"
        if not lag.lstrip("-").isdigit():
            raise ValueError("El desfase debe ser un número entero de días.")
        dependency = TaskDependency(
            predecessor_id=predecessor.id,
            successor_id=successor.id,
            dependency_type=v.choice("dependency_type", "El tipo de dependencia", TaskDependency.dependency_type, "FS"),
            lag_days=int(lag),
        )
        validate_dependency(db.session, dependency)
        db.session.add(dependency)
        record_audit(
            "task_dependency.created",
            f"Dependencia {dependency.dependency_type} «{predecessor.name}» → «{successor.name}» creada",
            project,
        )
        db.session.commit()
        return {"message": "Dependencia creada."}, 201
    except ValueError as error:
        db.session.rollback()
        return {"error": str(error)}, 400


@work_bp.post("/<string:project_id>/<string:kind>/<string:item_id>/delete")
@load_project
def delete_work_item(project: Project, kind: str, item_id: str) -> Any:
    """Elimina una tarea, recurso o hito del proyecto según el rol requerido."""
    require_role(KIND_MIN_ROLE.get(kind, "gestor"))
    item = _project_item(project, kind, item_id)
    record_audit(f"{kind}.deleted", _describe(kind, item.name, "deleted"), project)
    db.session.delete(item)
    db.session.commit()
    flash(MESSAGES[kind]["deleted"], "success")
    return redirect(url_for("projects.detail", project_id=project.id, vista=KIND_TABS[kind]))


def _member(project: Project, member_id: str) -> ProjectMember:
    """Entrada de la lista de usuarios del proyecto o 404."""
    member = db.session.scalar(
        select(ProjectMember).where(ProjectMember.id == member_id, ProjectMember.project_id == project.id)
    )
    if member is None:
        abort(404)
    return member


def _keeps_an_admin(project: Project, leaving: ProjectMember) -> bool:
    """El proyecto debe conservar al menos un administrador."""
    return db.session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.role == "admin",
            ProjectMember.id != leaving.id,
        )
    ) is not None


def _to_members(project: Project) -> Any:
    return redirect(url_for("projects.detail", project_id=project.id, vista="usuarios"))


@work_bp.post("/<string:project_id>/members")
@load_project
def add_member(project: Project) -> Any:
    """Agrega un correo a la lista de usuarios con un rol (solo administradores)."""
    require_role("admin")
    try:
        address = v.email("email", "El correo")
        role = v.choice("role", "El rol", ProjectMember.role)
        if db.session.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.email == address)
        ):
            raise ValueError(f"{address} ya está en la lista de usuarios del proyecto.")
        db.session.add(ProjectMember(project_id=project.id, email=address, role=role))
        record_audit("member.added", f"Usuario {address} agregado como {role}", project)
        db.session.commit()
        flash(f"{address} agregado como {role}. Verá el proyecto al iniciar sesión o registrarse.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    return _to_members(project)


@work_bp.post("/<string:project_id>/members/<string:member_id>/role")
@load_project
def change_member_role(project: Project, member_id: str) -> Any:
    """Cambia el rol de un usuario de la lista (solo administradores)."""
    require_role("admin")
    member = _member(project, member_id)
    try:
        role = v.choice("role", "El rol", ProjectMember.role)
        if member.role == "admin" and role != "admin" and not _keeps_an_admin(project, member):
            raise ValueError("El proyecto debe tener al menos un administrador.")
        previous, member.role = member.role, role
        record_audit("member.role_changed", f"Rol de {member.email}: {previous} → {role}", project)
        db.session.commit()
        flash(f"Rol de {member.email} actualizado a {role}.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    return _to_members(project)


@work_bp.post("/<string:project_id>/members/<string:member_id>/delete")
@load_project
def remove_member(project: Project, member_id: str) -> Any:
    """Quita un correo de la lista de usuarios (solo administradores)."""
    require_role("admin")
    member = _member(project, member_id)
    if member.role == "admin" and not _keeps_an_admin(project, member):
        flash("El proyecto debe tener al menos un administrador.", "error")
        return _to_members(project)
    record_audit("member.removed", f"Usuario {member.email} quitado de la lista", project)
    db.session.delete(member)
    db.session.commit()
    flash(f"{member.email} ya no tiene acceso al proyecto.", "success")
    if member.email == g.user.email:
        return redirect(url_for("projects.dashboard"))
    return _to_members(project)


def _task_editor(project: Project, task_id: str) -> Any:
    return redirect(url_for("work.edit_work_item", project_id=project.id, kind="task", item_id=task_id) + "#recursos")


@work_bp.post("/<string:project_id>/tasks/<string:task_id>/assignments")
@load_project
def save_assignment(project: Project, task_id: str) -> Any:
    """Asigna un recurso a la tarea o actualiza sus unidades planificadas y reales (jefe o gerente)."""
    require_role("gestor")
    task = _project_item(project, "task", task_id)
    try:
        resource = db.session.scalar(
            select(Resource).where(
                Resource.id == request.form.get("resource_id", ""), Resource.project_id == project.id
            )
        )
        if resource is None:
            raise ValueError("Seleccione un recurso del proyecto.")
        planned = v.decimal("planned_units", "Las unidades planificadas", maximum=Decimal(1000))
        actual = v.decimal("actual_units", "Las unidades reales", maximum=Decimal(1000))
        assignment = db.session.get(TaskResourceAssignment, (task.id, resource.id))
        if assignment is None:
            assignment = TaskResourceAssignment(task_id=task.id, resource_id=resource.id)
            db.session.add(assignment)
        assignment.planned_units, assignment.actual_units = planned, actual
        record_audit(
            "assignment.saved",
            f"Recurso «{resource.name}» en tarea «{task.name}»: plan {planned}, real {actual}",
            project,
        )
        db.session.commit()
        flash(f"Asignación de «{resource.name}» guardada.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
    return _task_editor(project, task.id)


@work_bp.post("/<string:project_id>/tasks/<string:task_id>/assignments/<string:resource_id>/delete")
@load_project
def delete_assignment(project: Project, task_id: str, resource_id: str) -> Any:
    """Quita un recurso de la tarea (jefe o gerente)."""
    require_role("gestor")
    task = _project_item(project, "task", task_id)
    assignment = db.session.get(TaskResourceAssignment, (task.id, resource_id))
    if assignment is None:
        abort(404)
    record_audit("assignment.deleted", f"Recurso quitado de la tarea «{task.name}»", project)
    db.session.delete(assignment)
    db.session.commit()
    flash("Asignación eliminada.", "success")
    return _task_editor(project, task.id)
