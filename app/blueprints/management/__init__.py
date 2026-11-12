"""Endpoints de KPI y gestión del cambio."""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select

from ...extensions import db
from ...models import (
    ChangeRequest,
    KpiAlert,
    KpiDefinition,
    KpiMeasurement,
    Project,
    ProjectMembership,
    Resource,
    Task,
)
from ...services.change_service import ChangeError, approve_change, transition_change
from ...services.kpi_engine import KpiError, evaluate_kpi, validate_definition
from ..projects import project_access_required

management_bp = Blueprint("management", __name__, url_prefix="/api/projects")


def _can_approve(project: Project) -> bool:
    """Solo el administrador o el director del proyecto pueden aprobar."""
    return current_user.is_admin or project.director_id == current_user.id


def _can_manage_change(project: Project) -> bool:
    """Permite actualizar etapas a administradores, director o manager."""
    return _can_approve(project) or db.session.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project.id,
            ProjectMembership.user_id == current_user.id,
            ProjectMembership.membership_role == "manager",
        )
    ) is not None


def _can_manage_kpi(project: Project) -> bool:
    """Permite administrar KPI a administradores, director o manager."""
    return _can_manage_change(project)


def _change_form_impact() -> dict:
    """Construye el impacto estructurado desde el formulario visible."""
    task_id = request.form.get("impact_task_id", "").strip()
    resource_id = request.form.get("impact_resource_id", "").strip()
    impact: dict[str, object] = {}
    days = request.form.get("additional_days", "").strip()
    cost = request.form.get("additional_cost", "").strip()
    hours = request.form.get("additional_hours", "").strip()
    if days:
        try:
            parsed_days = int(days)
        except ValueError as error:
            raise ValueError("Los días adicionales deben ser un número entero.") from error
        if parsed_days < 0:
            raise ValueError("Los días adicionales no pueden ser negativos.")
        if not task_id:
            raise ValueError("Selecciona la actividad para aplicar los días adicionales.")
        impact["additional_days"] = {"task_id": task_id, "days": parsed_days}
    if cost:
        parsed_cost = _decimal_field("additional_cost")
        if parsed_cost is None or parsed_cost < 0:
            raise ValueError("El costo adicional no puede ser negativo.")
        impact["additional_cost"] = str(parsed_cost)
    if hours:
        parsed_hours = _decimal_field("additional_hours")
        if parsed_hours is None or parsed_hours < 0:
            raise ValueError("Las horas adicionales no pueden ser negativas.")
        if not task_id or not resource_id:
            raise ValueError("Selecciona actividad y recurso para agregar horas.")
        impact["additional_resource"] = {
            "task_id": task_id,
            "resource_id": resource_id,
            "hours": str(parsed_hours),
        }
    if not impact:
        raise ValueError("Indica al menos un impacto: días, costo u horas.")
    return impact


def _change_form_context(project: Project, change: ChangeRequest | None = None) -> dict:
    tasks = db.session.scalars(
        select(Task).where(Task.project_id == project.id).order_by(Task.name)
    ).all()
    resources = db.session.scalars(
        select(Resource).where(Resource.project_id == project.id).order_by(Resource.name)
    ).all()
    return {"project": project, "change": change, "tasks": tasks, "resources": resources}


def _parse_date_field(name: str) -> date | None:
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} debe usar el formato AAAA-MM-DD.") from error


def _fill_change_from_form(change: ChangeRequest) -> None:
    """Valida y carga los campos editables de una solicitud."""
    code = request.form.get("change_code", "").strip().upper()
    description = request.form.get("description", "").strip()
    change_type = request.form.get("change_type", "").strip()
    priority = request.form.get("priority", "").strip()
    risk = request.form.get("risk", "").strip()
    if not code or not description:
        raise ValueError("El identificador y la descripción son obligatorios.")
    if change_type not in {"alcance", "tiempo", "costo", "recurso", "tecnologia", "organizacion"}:
        raise ValueError("El tipo de cambio no es válido.")
    if priority not in {"baja", "media", "alta", "critica"}:
        raise ValueError("La prioridad no es válida.")
    if risk not in {"bajo", "medio", "alto", "critico"}:
        raise ValueError("El riesgo no es válido.")
    if change.id is None:
        duplicate = db.session.scalar(
            select(ChangeRequest).where(
                ChangeRequest.project_id == change.project_id,
                ChangeRequest.change_code == code,
            )
        )
        if duplicate:
            raise ValueError("Ya existe una solicitud con ese identificador.")
    change.change_code = code
    change.description = description
    change.justification = request.form.get("justification", "").strip() or None
    change.change_type = change_type
    change.priority = priority
    change.risk = risk
    change.committed_date = _parse_date_field("committed_date")
    change.estimated_cost = _decimal_field("estimated_cost") or Decimal(0)
    if change.estimated_cost < 0:
        raise ValueError("El costo estimado no puede ser negativo.")
    change.evidence = request.form.get("evidence", "").strip() or None
    change.impact = _change_form_impact()


@management_bp.route("/<string:project_id>/changes/new", methods=["GET", "POST"])
@project_access_required
def create_change(project: Project):
    """Presenta el formulario accesible para registrar una solicitud."""
    change = ChangeRequest(project_id=project.id, requester_id=current_user.id)
    if request.method == "POST":
        try:
            _fill_change_from_form(change)
            db.session.add(change)
            db.session.commit()
            flash("Solicitud de cambio registrada.", "success")
            return redirect(url_for("dashboards.changes_page", project_id=project.id))
        except (ValueError, TypeError, KpiError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("management/change_form.html", **_change_form_context(project, change))


@management_bp.route(
    "/<string:project_id>/changes/<string:change_id>/edit",
    methods=["GET", "POST"],
)
@project_access_required
def edit_change(project: Project, change_id: str):
    """Edita una solicitud mientras aún no está aprobada."""
    if not _can_manage_change(project):
        abort(403)
    change = db.session.scalar(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id,
            ChangeRequest.project_id == project.id,
        )
    )
    if change is None:
        abort(404)
    if change.status == "approved":
        flash("Una solicitud aprobada ya no se puede editar.", "error")
        return redirect(url_for("dashboards.changes_page", project_id=project.id))
    if request.method == "POST":
        try:
            _fill_change_from_form(change)
            db.session.commit()
            flash("Solicitud de cambio actualizada.", "success")
            return redirect(url_for("dashboards.changes_page", project_id=project.id))
        except (ValueError, TypeError, KpiError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("management/change_form.html", **_change_form_context(project, change))


def _decimal_field(name: str, required: bool = True) -> Decimal | None:
    value = request.form.get(name, "").strip()
    if not value and not required:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise KpiError(f"{name} debe ser un número válido.") from error


def _thresholds_from_form(direction: str) -> dict[str, str]:
    if direction == "range":
        minimum = _decimal_field("threshold_min")
        maximum = _decimal_field("threshold_max")
        if minimum is None or maximum is None or minimum > maximum:
            raise KpiError("El rango mínimo y máximo no es válido.")
        return {"min": str(minimum), "max": str(maximum)}
    green = _decimal_field("threshold_green")
    yellow = _decimal_field("threshold_yellow")
    if green is None or yellow is None:
        raise KpiError("Debes indicar los umbrales verde y amarillo.")
    return {"green": str(green), "yellow": str(yellow)}


def _fill_kpi_from_form(kpi: KpiDefinition) -> None:
    """Carga y valida los campos simples del formulario de KPI."""
    code = request.form.get("code", "").strip().upper()
    name = request.form.get("name", "").strip()
    variables = [
        value.strip()
        for value in request.form.get("variables", "").split(",")
        if value.strip()
    ]
    scope = request.form.get("scope", "")
    direction = request.form.get("direction", "")
    source = request.form.get("source", "")
    if not code or not name or not variables:
        raise KpiError("Código, nombre y variables son obligatorios.")
    if scope not in {"project", "task", "milestone", "change"}:
        raise KpiError("El ámbito seleccionado no es válido.")
    if direction not in {"higher", "lower", "range"}:
        raise KpiError("El sentido seleccionado no es válido.")
    if source not in {"automatic", "manual"}:
        raise KpiError("La fuente seleccionada no es válida.")
    kpi.code = code
    kpi.name = name
    kpi.objective = request.form.get("objective", "").strip() or None
    kpi.scope = scope
    kpi.variables = variables
    kpi.formula = request.form.get("formula", "").strip()
    kpi.unit = request.form.get("unit", "").strip() or None
    kpi.target = _decimal_field("target")
    kpi.direction = direction
    kpi.thresholds = _thresholds_from_form(direction)
    kpi.periodicity = request.form.get("periodicity", "manual").strip()
    kpi.source = source
    validate_definition(kpi)


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


@management_bp.route("/<string:project_id>/kpis", methods=["GET", "POST"])
@project_access_required
def kpi_list(project: Project):
    """Muestra y crea definiciones de KPI del proyecto."""
    if not _can_manage_kpi(project):
        abort(403)
    if request.method == "POST":
        kpi = KpiDefinition(project_id=project.id)
        try:
            _fill_kpi_from_form(kpi)
            if db.session.scalar(
                select(KpiDefinition).where(
                    KpiDefinition.project_id == project.id,
                    KpiDefinition.code == kpi.code,
                )
            ):
                raise KpiError("Ya existe un KPI con ese código.")
            db.session.add(kpi)
            db.session.commit()
            flash("KPI creado correctamente.", "success")
            return redirect(url_for("management.kpi_list", project_id=project.id))
        except (KpiError, TypeError, ValueError) as error:
            db.session.rollback()
            flash(str(error), "error")
    kpis = db.session.scalars(
        select(KpiDefinition)
        .where(KpiDefinition.project_id == project.id)
        .order_by(KpiDefinition.code)
    ).all()
    history = {
        kpi.id: db.session.scalars(
            select(KpiMeasurement)
            .where(KpiMeasurement.kpi_id == kpi.id)
            .order_by(KpiMeasurement.measured_at.desc())
            .limit(10)
        ).all()
        for kpi in kpis
    }
    alerts = {
        kpi.id: db.session.scalars(
            select(KpiAlert)
            .where(KpiAlert.kpi_id == kpi.id)
            .order_by(KpiAlert.created_at.desc())
            .limit(10)
        ).all()
        for kpi in kpis
    }
    return render_template(
        "management/kpis.html",
        project=project,
        kpis=kpis,
        history=history,
        alerts=alerts,
        form_kpi=KpiDefinition(scope="project", direction="higher", source="manual"),
    )


@management_bp.route("/<string:project_id>/kpis/<string:kpi_id>/edit", methods=["GET", "POST"])
@project_access_required
def edit_kpi(project: Project, kpi_id: str):
    """Edita una definición de KPI del proyecto."""
    if not _can_manage_kpi(project):
        abort(403)
    kpi = db.session.scalar(
        select(KpiDefinition).where(
            KpiDefinition.id == kpi_id,
            KpiDefinition.project_id == project.id,
        )
    )
    if kpi is None:
        abort(404)
    if request.method == "POST":
        try:
            _fill_kpi_from_form(kpi)
            db.session.commit()
            flash("KPI actualizado correctamente.", "success")
            return redirect(url_for("management.kpi_list", project_id=project.id))
        except (KpiError, TypeError, ValueError) as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template(
        "management/kpi_edit.html",
        project=project,
        kpi=kpi,
    )


@management_bp.post("/<string:project_id>/kpis/<string:kpi_id>/manual-measure")
@project_access_required
def manual_measure_kpi(project: Project, kpi_id: str):
    """Guarda una medición agregada de adopción, satisfacción o resistencia."""
    if not _can_manage_kpi(project):
        abort(403)
    kpi = db.session.scalar(
        select(KpiDefinition).where(
            KpiDefinition.id == kpi_id,
            KpiDefinition.project_id == project.id,
        )
    )
    if kpi is None:
        abort(404)
    try:
        value = _decimal_field("manual_value")
        if value is None or value < 1 or value > 5:
            raise KpiError("El valor agregado debe estar entre 1 y 5.")
        if kpi.code not in {"CHG-ADOPCION", "CHG-SATISFACCION", "CHG-RESISTENCIA"}:
            raise KpiError("Este KPI no usa una medición agregada de escala 1 a 5.")
        evaluate_kpi(db.session, kpi, {kpi.variables[0]: value})
        db.session.commit()
        flash("Medición agregada guardada.", "success")
    except (KpiError, TypeError, ValueError) as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("management.kpi_list", project_id=project.id))


@management_bp.post("/<string:project_id>/kpis/<string:kpi_id>/delete")
@project_access_required
def delete_kpi(project: Project, kpi_id: str):
    """Elimina una definición de KPI y su historial asociado."""
    if not _can_manage_kpi(project):
        abort(403)
    kpi = db.session.scalar(
        select(KpiDefinition).where(
            KpiDefinition.id == kpi_id,
            KpiDefinition.project_id == project.id,
        )
    )
    if kpi is None:
        abort(404)
    if kpi.milestones:
        flash(
            "No se puede eliminar este KPI porque está asociado a un hito. "
            "Quita primero esa asociación.",
            "error",
        )
        return redirect(url_for("management.kpi_list", project_id=project.id))
    db.session.delete(kpi)
    db.session.commit()
    flash("KPI eliminado correctamente.", "success")
    return redirect(url_for("management.kpi_list", project_id=project.id))


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


@management_bp.post("/<string:project_id>/changes/<string:change_id>/stage")
@project_access_required
def advance_stage(project: object, change_id: str):
    """Avanza una sola etapa y guarda el comentario de trazabilidad."""
    if not _can_manage_change(project):
        abort(403)
    change = db.session.scalar(
        select(ChangeRequest).where(
            ChangeRequest.id == change_id, ChangeRequest.project_id == project.id
        )
    )
    if change is None:
        abort(404)
    body = request.get_json(silent=True) or {}
    try:
        history = transition_change(
            db.session,
            change,
            current_user.id,
            str(body.get("comment", "")),
        )
        db.session.commit()
        return jsonify(
            {
                "stage": change.stage,
                "status": change.status,
                "history_id": history.id,
            }
        )
    except (ChangeError, TypeError, ValueError) as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 400
