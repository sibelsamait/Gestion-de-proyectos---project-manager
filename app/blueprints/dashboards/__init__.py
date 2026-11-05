"""Gantt y tableros JSON protegidos por proyecto."""

from flask import Blueprint, jsonify, render_template

from ...extensions import db
from ...services.dashboard import change_dashboard, gantt_data, tracking_dashboard
from ..projects import project_access_required

dashboards_bp = Blueprint("dashboards", __name__)


@dashboards_bp.get("/api/projects/<string:project_id>/gantt")
@project_access_required
def gantt(project):
    """Devuelve tareas, hitos y precedencias del Gantt."""
    return jsonify(gantt_data(db.session, project.id))


@dashboards_bp.get("/api/projects/<string:project_id>/tracking")
@project_access_required
def tracking(project):
    """Devuelve datos del tablero de seguimiento."""
    return jsonify(tracking_dashboard(db.session, project))


@dashboards_bp.get("/api/projects/<string:project_id>/changes-dashboard")
@project_access_required
def changes_dashboard(project):
    """Devuelve datos del tablero de gestión del cambio."""
    return jsonify(change_dashboard(db.session, project.id))


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
