"""Endpoints de KPI y gestión del cambio."""

from decimal import InvalidOperation

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from ...extensions import db
from ...models import ChangeRequest, KpiDefinition, Project
from ...services.change_service import ChangeError, approve_change
from ...services.kpi_engine import KpiError, evaluate_kpi
from ..projects import project_access_required

management_bp = Blueprint("management", __name__, url_prefix="/api/projects")


def _can_approve(project: Project) -> bool:
    """Solo el administrador o el director del proyecto pueden aprobar."""
    return current_user.is_admin or project.director_id == current_user.id


@management_bp.post("/<string:project_id>/kpis/<string:kpi_id>/measure")
@project_access_required
def measure_kpi(project: object, kpi_id: str):
    """Evalúa un KPI con variables recibidas como JSON."""
    kpi = db.session.scalar(
        select(KpiDefinition).where(KpiDefinition.id == kpi_id, KpiDefinition.project_id == project.id)
    )
    if kpi is None:
        abort(404)
    try:
        values = request.get_json(silent=False)
        if not isinstance(values, dict):
            raise KpiError("El cuerpo debe ser un objeto JSON.")
        measurement = evaluate_kpi(db.session, kpi, values)
        db.session.commit()
        return jsonify(
            {"result": str(measurement.result), "status": measurement.status, "measurement_id": measurement.id}
        )
    except (KpiError, TypeError, ValueError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400


@management_bp.post("/<string:project_id>/changes/<string:change_id>/approve")
@project_access_required
def approve(project: object, change_id: str):
    """Aprueba una solicitud solo para administrador o director."""
    if not _can_approve(project):
        abort(403)
    change = db.session.scalar(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id, ChangeRequest.project_id == project.id
        )
    )
    if change is None:
        abort(404)
    try:
        applications = approve_change(db.session, change, "admin" if current_user.is_admin else "director")
        db.session.commit()
        return jsonify({"status": change.status, "applications": len(applications)})
    except (ChangeError, ValueError, InvalidOperation) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
