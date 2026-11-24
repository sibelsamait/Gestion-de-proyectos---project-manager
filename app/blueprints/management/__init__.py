"""Endpoints de KPI y gestión del cambio."""

from decimal import InvalidOperation

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import select

from ...extensions import db
from ...models import ChangeRequest, KpiDefinition
from ...services.audit import record_audit
from ...services.change_service import ChangeError, approve_change
from ...services.kpi_engine import KpiError, evaluate_kpi
from ..projects import load_project, require_role

management_bp = Blueprint("management", __name__, url_prefix="/api/projects")


@management_bp.post("/<string:project_id>/kpis/<string:kpi_id>/measure")
@load_project
def measure_kpi(project: object, kpi_id: str):
    """Evalúa un KPI con variables recibidas como JSON."""
    require_role("gestor")
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
        record_audit("kpi.measured", f"KPI {kpi.code} medido: {measurement.result} ({measurement.status})", project)
        db.session.commit()
        return jsonify(
            {"result": str(measurement.result), "status": measurement.status, "measurement_id": measurement.id}
        )
    except (KpiError, TypeError, ValueError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400


@management_bp.post("/<string:project_id>/changes/<string:change_id>/approve")
@load_project
def approve(project: object, change_id: str):
    """Aprueba una solicitud en etapa Decisión y aplica su impacto (gerente: afecta presupuesto)."""
    require_role("admin")
    change = db.session.scalar(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id, ChangeRequest.project_id == project.id
        )
    )
    if change is None:
        abort(404)
    try:
        applications = approve_change(db.session, change, "admin")
        record_audit(
            "change.approved",
            f"Solicitud {change.change_code} aprobada; {len(applications)} cambio(s) aplicado(s)",
            project,
        )
        db.session.commit()
        return jsonify({"status": change.status, "applications": len(applications)})
    except (ChangeError, ValueError, InvalidOperation) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
