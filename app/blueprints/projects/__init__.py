"""Portafolio y detalle de proyectos."""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import (
    Blueprint,
    abort,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from ...extensions import db
from ...models import ROLE_RANK, Project, ProjectMember
from ...services.project_overview import (
    portfolio_rows,
    project_overview,
    resolve_money_context,
)

DETAIL_TABS = (
    "resumen", "preinversion", "alcance", "tareas", "hitos", "recursos", "riesgos", "kpi", "cambios", "usuarios",
)

projects_bp = Blueprint("projects", __name__)


def role_in_project(project_id: str) -> str | None:
    """Rol del usuario actual en el proyecto según la lista de usuarios, o None."""
    return db.session.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.email == g.user.email,
        )
    )


def load_project(view: Callable[..., Any]) -> Callable[..., Any]:
    """Carga el proyecto de la URL; solo pasan los correos incluidos en su lista de usuarios."""

    @wraps(view)
    def wrapped(project_id: str, *args: Any, **kwargs: Any) -> Any:
        project = db.session.get(Project, project_id)
        if project is None:
            abort(404)
        role = role_in_project(project.id)
        if role is None:
            abort(403)
        g.project = project
        g.project_role = role
        return view(project, *args, **kwargs)

    return wrapped


def has_role(minimum: str) -> bool:
    """Indica si el rol del usuario en el proyecto cargado alcanza el mínimo pedido."""
    role = g.get("project_role")
    return role is not None and ROLE_RANK[role] >= ROLE_RANK[minimum]


def require_role(minimum: str) -> None:
    """Responde 403 si el rol del usuario no alcanza el mínimo."""
    if not has_role(minimum):
        abort(403)


def display_money() -> tuple[dict, bool]:
    """Contexto monetario de la sesión con degradación a CLP sin tasas."""
    return resolve_money_context(session.get("currency", "CLP"), db.session)


@projects_bp.get("/")
def index() -> str:
    """Entrada de la aplicación."""
    return redirect(url_for("projects.dashboard"))


@projects_bp.get("/dashboard")
def dashboard() -> str:
    """Lista los proyectos donde el correo del usuario figura en la lista de usuarios."""
    memberships = dict(
        db.session.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.email == g.user.email)
        ).all()
    )
    projects = db.session.scalars(
        select(Project).where(Project.id.in_(list(memberships))).order_by(Project.name)
    ).all() if memberships else []
    money, fallback = display_money()
    rows = portfolio_rows(db.session, projects, money)
    status_filter = request.args.get("estado", "")
    for row in rows:
        row["role"] = memberships[row["project"].id]
    visible = [row for row in rows if not status_filter or row["project"].status == status_filter]
    totals = {
        "projects": len(rows),
        "active": sum(1 for row in rows if row["project"].status == "en_ejecucion"),
        "overdue": sum(row["tasks_overdue"] for row in rows),
        "budget": sum((row["budget"] for row in rows), 0),
    }
    return render_template(
        "projects/dashboard.html",
        rows=visible,
        totals=totals,
        status_filter=status_filter,
        money=money,
        currency_fallback=fallback,
    )


@projects_bp.get("/projects/<string:project_id>")
@load_project
def detail(project: Project) -> str:
    """Vista de gestión del proyecto, organizada por pestañas."""
    tab = request.args.get("vista", "resumen")
    if tab not in DETAIL_TABS:
        tab = "resumen"
    money, fallback = display_money()
    return render_template(
        "projects/detail.html",
        project=project,
        overview=project_overview(db.session, project, money),
        tab=tab,
        currency_fallback=fallback,
    )
