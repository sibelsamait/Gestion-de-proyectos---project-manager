"""Gantt y tableros JSON protegidos por proyecto."""

from flask import Blueprint, jsonify, render_template, request

from ...extensions import db
from ...services.currency import validate_currency
from ...services.dashboard import change_dashboard, gantt_data, tracking_dashboard
from ..projects import project_access_required

dashboards_bp = Blueprint("dashboards", __name__)


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
            gantt_data(db.session, project.id, currency, request.args.get("scale", "day"))
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
    return jsonify(tracking_dashboard(db.session, project, currency))


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
    return render_template("dashboards/tracking.html", project=project)


@dashboards_bp.get("/projects/<string:project_id>/changes")
@project_access_required
def changes_page(project):
    """Renderiza el tablero de cambios."""
    return render_template("dashboards/changes.html", project=project)
