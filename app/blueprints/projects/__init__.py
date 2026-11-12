"""Dashboard y autorización por proyecto."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, abort, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from ...models import (
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    ProjectMembership,
    Resource,
    Task,
    TaskDependency,
)

projects_bp = Blueprint("projects", __name__)


def project_access_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """Restringe una vista a administradores o miembros del proyecto."""

    @wraps(view)
    @login_required
    def wrapped(project_id: str, *args: Any, **kwargs: Any) -> Any:
        project = db_session_get_project(project_id)
        if project is None:
            abort(404)
        if not current_user.is_admin:
            membership = ProjectMembership.query.filter_by(
                project_id=project_id, user_id=current_user.id
            ).first()
            if membership is None:
                abort(403)
        session["active_project_id"] = project_id
        return view(project, *args, **kwargs)

    return wrapped


def db_session_get_project(project_id: str) -> Project | None:
    """Obtiene el proyecto por ORM, sin interpolar SQL."""
    return Project.query.filter_by(id=project_id).first()


@projects_bp.get("/")
def index() -> str:
    """Página pública de entrada."""
    if current_user.is_authenticated:
        return redirect(url_for("projects.dashboard"))
    return redirect(url_for("auth.login"))


@projects_bp.get("/dashboard")
@login_required
def dashboard() -> str:
    """Lista únicamente proyectos autorizados."""
    if current_user.is_admin:
        projects = Project.query.order_by(Project.name).all()
    else:
        projects = (
            Project.query.join(ProjectMembership)
            .filter(ProjectMembership.user_id == current_user.id)
            .order_by(Project.name)
            .all()
        )
    return render_template("projects/dashboard.html", projects=projects)


@projects_bp.get("/projects/<string:project_id>")
@project_access_required
def detail(project: Project) -> str:
    """Selecciona el proyecto activo tras comprobar autorización."""
    counts = {
        "tasks": Task.query.filter_by(project_id=project.id).count(),
        "dependencies": (
            TaskDependency.query.join(Task, Task.id == TaskDependency.predecessor_id)
            .filter(Task.project_id == project.id)
            .count()
        ),
        "resources": Resource.query.filter_by(project_id=project.id).count(),
        "milestones": Milestone.query.filter_by(project_id=project.id).count(),
        "kpis": KpiDefinition.query.filter_by(project_id=project.id).count(),
        "changes": ChangeRequest.query.filter_by(project_id=project.id).count(),
    }
    definitions = (
        ("Datos del proyecto", bool(project.name and project.code), "edit", "Define o revisa los datos básicos."),
        ("Actividades", counts["tasks"] > 0, "task", "Crea la primera actividad."),
        ("Relaciones entre actividades", counts["dependencies"] > 0, "tracking", "Agrega una dependencia entre actividades."),
        ("Recursos y costos", counts["resources"] > 0, "resource", "Registra al menos un recurso."),
        ("Hitos", counts["milestones"] > 0, "milestone", "Registra un hito comprometido."),
        ("Indicadores", counts["kpis"] > 0, "tracking", "Crea o revisa los indicadores."),
        ("Cambios", counts["changes"] > 0, "changes", "Registra una solicitud de cambio."),
        ("Tableros", True, "tracking", "Consulta los resultados del proyecto."),
        ("Informe PDF", True, "pdf", "Descarga el resumen del proyecto."),
    )
    guided_steps = []
    previous_complete = True
    for name, complete, target, help_text in definitions:
        status = "completo" if complete else ("pendiente" if previous_complete else "bloqueado")
        if not complete:
            previous_complete = False
        guided_steps.append(
            {
                "name": name,
                "status": status,
                "target": target,
                "help": help_text,
                "complete": complete,
            }
        )
    return render_template(
        "projects/detail.html",
        project=project,
        guided_steps=guided_steps,
        counts=counts,
    )
