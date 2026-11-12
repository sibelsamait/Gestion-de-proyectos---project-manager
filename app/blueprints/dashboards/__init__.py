"""Gantt y tableros JSON protegidos por proyecto."""

from datetime import date

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import select

from ...extensions import db
from ...models import Task, User
from ...services.currency import validate_currency
from ...services.dashboard import change_dashboard, gantt_data, tracking_dashboard
from ..projects import project_access_required

dashboards_bp = Blueprint("dashboards", __name__)


def _query_date(name: str) -> date | None:
    value = request.args.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} debe usar el formato AAAA-MM-DD.") from error


@dashboards_bp.get("/api/projects/<string:project_id>/gantt")
@project_access_required
def gantt(project):
    """Devuelve tareas, hitos y precedencias del Gantt."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    try:
        return jsonify(
            gantt_data(
                db.session,
                project.id,
                currency,
                request.args.get("scale", "day"),
                request.args.get("stage"),
                _query_date("date_from"),
                _query_date("date_to"),
                request.args.get("responsible_id"),
            )
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@dashboards_bp.get("/api/projects/<string:project_id>/tracking")
@project_access_required
def tracking(project):
    """Devuelve datos del tablero de seguimiento."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    try:
        return jsonify(
            tracking_dashboard(
                db.session,
                project,
                currency,
                request.args.get("stage"),
                _query_date("date_from"),
                _query_date("date_to"),
                request.args.get("responsible_id"),
            )
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@dashboards_bp.get("/api/projects/<string:project_id>/changes-dashboard")
@project_access_required
def changes_dashboard(project):
    """Devuelve datos del tablero de gestión del cambio."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(
        change_dashboard(
            db.session,
            project.id,
            currency,
            status=request.args.get("status"),
            priority=request.args.get("priority"),
            change_type=request.args.get("type"),
            responsible_id=request.args.get("responsible_id"),
        )
    )


@dashboards_bp.get("/projects/<string:project_id>/tracking")
@project_access_required
def tracking_page(project):
    """Renderiza el tablero de seguimiento."""
    stages = db.session.scalars(
        select(Task.etapa)
        .where(Task.project_id == project.id, Task.etapa.is_not(None))
        .distinct()
        .order_by(Task.etapa)
    ).all()
    responsible_ids = db.session.scalars(
        select(Task.responsible_id)
        .where(Task.project_id == project.id, Task.responsible_id.is_not(None))
        .distinct()
    ).all()
    responsible_options = [
        (user.id, user.name)
        for user in db.session.scalars(
            select(User).where(User.id.in_(responsible_ids)).order_by(User.name)
        )
    ]
    return render_template(
        "dashboards/tracking.html",
        project=project,
        stages=stages,
        responsible_options=responsible_options,
    )


@dashboards_bp.get("/projects/<string:project_id>/changes")
@project_access_required
def changes_page(project):
    """Renderiza el tablero de cambios."""
    return render_template("dashboards/changes.html", project=project)
