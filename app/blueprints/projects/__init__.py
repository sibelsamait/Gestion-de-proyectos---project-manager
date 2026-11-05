"""Dashboard y autorización por proyecto."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, abort, redirect, render_template, session, url_for
from flask_login import current_user, login_required

from ...models import Project, ProjectMembership

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
    return render_template("projects/detail.html", project=project)
