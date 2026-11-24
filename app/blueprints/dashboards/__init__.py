"""Gantt y tableros JSON protegidos por proyecto."""

from flask import Blueprint, jsonify, render_template, request

from ...extensions import db
from ...services.currency import validate_currency
from ...services.dashboard import change_dashboard, gantt_data, tracking_dashboard
from ..projects import load_project

dashboards_bp = Blueprint("dashboards", __name__)


@dashboards_bp.get("/api/projects/<string:project_id>/gantt")
@load_project
def gantt(project):
    """Devuelve tareas, hitos y precedencias del Gantt."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(gantt_data(db.session, project.id, currency))


@dashboards_bp.get("/api/projects/<string:project_id>/tracking")
@load_project
def tracking(project):
    """Devuelve datos del tablero de seguimiento."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(tracking_dashboard(db.session, project, currency))


@dashboards_bp.get("/api/projects/<string:project_id>/changes-dashboard")
@load_project
def changes_dashboard(project):
    """Devuelve datos del tablero de gestión del cambio."""
    try:
        currency = validate_currency(request.args.get("currency"))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(change_dashboard(db.session, project.id, currency))


@dashboards_bp.get("/projects/<string:project_id>/tracking")
@load_project
def tracking_page(project):
    """Renderiza el tablero de seguimiento."""
    return render_template("dashboards/tracking.html", project=project)


@dashboards_bp.get("/projects/<string:project_id>/changes")
@load_project
def changes_page(project):
    """Renderiza el tablero de cambios."""
    return render_template("dashboards/changes.html", project=project)
