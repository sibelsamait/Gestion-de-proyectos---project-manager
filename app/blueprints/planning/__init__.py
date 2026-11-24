"""Preinversión, autorización, alcance y riesgos del proyecto."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select

from ... import validation as v
from ...extensions import db
from ...models import (
    STUDY_TYPES,
    CashFlow,
    PreinvestmentStudy,
    Project,
    Risk,
    ScopeItem,
)
from ...services.audit import record_audit
from ...services.planning import (
    SCOPE_TEMPLATES,
    apply_scope_template,
    authorization_gaps,
)
from ...ui import STUDY_TYPE_LABELS
from ..projects import load_project, require_role

planning_bp = Blueprint("planning", __name__, url_prefix="/projects")

MAX_EVALUATION_YEARS = 20


def _back(project: Project, tab: str, anchor: str = "") -> Any:
    return redirect(url_for("projects.detail", project_id=project.id, vista=tab) + (f"#{anchor}" if anchor else ""))


def _fail(error: ValueError) -> None:
    db.session.rollback()
    flash(str(error), "error")


# ------------------------------------------------------ Autorización y fase

@planning_bp.post("/<string:project_id>/authorization")
@load_project
def save_authorization(project: Project) -> Any:
    """Registra el documento formal que autoriza el proyecto y designa al Director(a) (gerente)."""
    require_role("admin")
    try:
        project.authorized_by = v.text("authorized_by", "Quien autoriza", Project.authorized_by)
        project.authorization_date = v.iso_date("authorization_date", "La fecha de autorización")
        project.authorization_reference = v.text(
            "authorization_reference", "El documento de autorización", Project.authorization_reference
        )
        project.authorization_notes = v.text("authorization_notes", "Las observaciones")
        project.director_id = v.user_ref("director_id", "El Director(a)", v.people(project.id))
        record_audit("project.authorization_saved", "Documento de autorización actualizado", project)
        db.session.commit()
        flash("Documento de autorización guardado.", "success")
    except ValueError as error:
        _fail(error)
    return _back(project, "preinversion", "autorizacion")


@planning_bp.post("/<string:project_id>/phase")
@load_project
def change_phase(project: Project) -> Any:
    """Pasa el proyecto a inversión (requiere autorización completa) o lo devuelve a preinversión."""
    require_role("admin")
    target = request.form.get("phase", "")
    if target == "inversion":
        gaps = authorization_gaps(project)
        if gaps:
            flash("No es posible pasar a la etapa de inversión. " + " ".join(gaps), "error")
            return _back(project, "preinversion", "autorizacion")
        project.phase = "inversion"
        record_audit("project.phase_changed", "Proyecto autorizado: pasa a etapa de inversión", project)
        flash("El proyecto pasó a la etapa de inversión. Ya puede iniciar su ejecución.", "success")
    elif target == "preinversion":
        if project.status in ("en_ejecucion", "terminado"):
            flash("Un proyecto en ejecución o terminado no puede volver a preinversión.", "error")
            return _back(project, "preinversion", "autorizacion")
        project.phase = "preinversion"
        record_audit("project.phase_changed", "Proyecto devuelto a preinversión", project)
        flash("El proyecto volvió a la etapa de preinversión.", "success")
    else:
        abort(400)
    db.session.commit()
    return _back(project, "preinversion", "autorizacion")


# ---------------------------------------------------------- Estudios previos

@planning_bp.post("/<string:project_id>/studies/<string:study_type>")
@load_project
def save_study(project: Project, study_type: str) -> Any:
    """Actualiza el estado y conclusión de un estudio de preinversión (gerente)."""
    require_role("admin")
    if study_type not in STUDY_TYPES:
        abort(404)
    try:
        study = db.session.scalar(
            select(PreinvestmentStudy).where(
                PreinvestmentStudy.project_id == project.id, PreinvestmentStudy.study_type == study_type
            )
        )
        if study is None:
            study = PreinvestmentStudy(project_id=project.id, study_type=study_type)
            db.session.add(study)
        study.status = v.choice("status", "El estado del estudio", PreinvestmentStudy.status)
        study.conclusion = v.text("conclusion", "La conclusión")
        study.reference = v.text("reference", "La referencia", PreinvestmentStudy.reference)
        if study.status == "completado" and not study.conclusion:
            raise ValueError("Un estudio completado debe registrar su conclusión.")
        study.updated_at = datetime.now(UTC)
        label = STUDY_TYPE_LABELS[study_type][0]
        record_audit("study.updated", f"{label}: {study.status}", project)
        db.session.commit()
        flash(f"{label} actualizado.", "success")
    except ValueError as error:
        _fail(error)
    return _back(project, "preinversion", f"estudio-{study_type}")


# ------------------------------------------------------ Evaluación económica

@planning_bp.post("/<string:project_id>/evaluation")
@load_project
def save_evaluation(project: Project) -> Any:
    """Guarda tasa de descuento, horizonte y flujos de caja por período (gerente)."""
    require_role("admin")
    try:
        rate = v.decimal("discount_rate", "La tasa de descuento", maximum=Decimal(100))
        raw_years = request.form.get("evaluation_years", "").strip() or str(project.evaluation_years)
        if not raw_years.isdigit() or not 1 <= int(raw_years) <= MAX_EVALUATION_YEARS:
            raise ValueError(f"El horizonte de evaluación debe estar entre 1 y {MAX_EVALUATION_YEARS} años.")
        years = int(raw_years)
        stored = {
            flow.period: flow
            for flow in db.session.scalars(select(CashFlow).where(CashFlow.project_id == project.id))
        }
        for period in range(years + 1):
            values = {
                field: v.decimal(f"{field}_{period}", f"{label} del año {period}")
                for field, label in (("investment", "La inversión"), ("income", "Los ingresos"), ("costs", "Los costos"))
            }
            flow = stored.pop(period, None)
            if flow is None:
                flow = CashFlow(project_id=project.id, period=period)
                db.session.add(flow)
            for field, value in values.items():
                setattr(flow, field, value)
        for leftover in stored.values():
            if leftover.period > years:
                db.session.delete(leftover)
        project.discount_rate, project.evaluation_years = rate, years
        record_audit("evaluation.saved", f"Evaluación económica actualizada (tasa {rate} %, {years} años)", project)
        db.session.commit()
        flash("Evaluación económica guardada.", "success")
    except ValueError as error:
        _fail(error)
    return _back(project, "preinversion", "evaluacion")


# ------------------------------------------------------------------ Alcance

def _scope_item(project: Project, item_id: str) -> ScopeItem:
    item = db.session.scalar(select(ScopeItem).where(ScopeItem.id == item_id, ScopeItem.project_id == project.id))
    if item is None:
        abort(404)
    return item


@planning_bp.route("/<string:project_id>/scope/new", methods=["GET", "POST"])
@planning_bp.route("/<string:project_id>/scope/<string:item_id>/edit", methods=["GET", "POST"])
@load_project
def scope_form(project: Project, item_id: str | None = None) -> Any:
    """Crea o edita un elemento del enunciado de alcance (gerente)."""
    require_role("admin")
    item = _scope_item(project, item_id) if item_id else ScopeItem(
        project_id=project.id, category=request.args.get("categoria", "requisito_funcional")
    )
    if request.method == "POST":
        try:
            item.category = v.choice("category", "La categoría", ScopeItem.category)
            item.description = v.text("description", "La descripción", required=True)
            item.acceptance_criteria = v.text("acceptance_criteria", "El criterio de aceptación")
            if item.id is None:
                item.position = (db.session.scalar(
                    select(func.max(ScopeItem.position)).where(ScopeItem.project_id == project.id)
                ) or 0) + 1
                db.session.add(item)
            record_audit("scope.saved", f"Alcance ({item.category}): {item.description[:80]}", project)
            db.session.commit()
            flash("Elemento de alcance guardado.", "success")
            return _back(project, "alcance")
        except ValueError as error:
            _fail(error)
    return render_template("planning/scope_form.html", project=project, item=item)


@planning_bp.post("/<string:project_id>/scope/<string:item_id>/delete")
@load_project
def delete_scope(project: Project, item_id: str) -> Any:
    require_role("admin")
    item = _scope_item(project, item_id)
    record_audit("scope.deleted", f"Alcance eliminado: {item.description[:80]}", project)
    db.session.delete(item)
    db.session.commit()
    flash("Elemento de alcance eliminado.", "success")
    return _back(project, "alcance")


@planning_bp.post("/<string:project_id>/scope/template")
@load_project
def scope_template(project: Project) -> Any:
    """Carga una plantilla de alcance; los elementos quedan editables (gerente)."""
    require_role("admin")
    key = request.form.get("template", "")
    try:
        added = apply_scope_template(db.session, project.id, key)
        record_audit("scope.template_applied", f"Plantilla de alcance «{SCOPE_TEMPLATES[key]['label']}»", project)
        db.session.commit()
        flash(f"Plantilla aplicada: {added} elemento(s) agregados. Ajústelos al proyecto.", "success")
    except ValueError as error:
        _fail(error)
    return _back(project, "alcance")


# ------------------------------------------------------------------ Riesgos

def _risk(project: Project, risk_id: str) -> Risk:
    risk = db.session.scalar(select(Risk).where(Risk.id == risk_id, Risk.project_id == project.id))
    if risk is None:
        abort(404)
    return risk


def _scale(name: str, label: str) -> int:
    value = request.form.get(name, "").strip()
    if value not in {"1", "2", "3", "4", "5"}:
        raise ValueError(f"{label} debe estar entre 1 y 5.")
    return int(value)


@planning_bp.route("/<string:project_id>/risks/new", methods=["GET", "POST"])
@planning_bp.route("/<string:project_id>/risks/<string:risk_id>/edit", methods=["GET", "POST"])
@load_project
def risk_form(project: Project, risk_id: str | None = None) -> Any:
    """Registra o actualiza un riesgo del proyecto (jefe o gerente)."""
    require_role("gestor")
    risk = _risk(project, risk_id) if risk_id else Risk(project_id=project.id, probability=3, impact=3)
    if request.method == "POST":
        try:
            risk.description = v.text("description", "La descripción del riesgo", required=True)
            risk.category = v.text("category", "La categoría", Risk.category)
            risk.probability = _scale("probability", "La probabilidad")
            risk.impact = _scale("impact", "El impacto")
            risk.response = v.choice("response", "La estrategia de respuesta", Risk.response)
            risk.response_plan = v.text("response_plan", "El plan de respuesta")
            risk.owner_id = v.user_ref("owner_id", "El responsable", v.people(project.id))
            risk.status = v.choice("status", "El estado", Risk.status, default="identificado")
            if risk.level in ("alto", "critico") and risk.response != "aceptar" and not risk.response_plan:
                raise ValueError("Un riesgo alto o crítico requiere un plan de respuesta.")
            if risk.id is None:
                db.session.add(risk)
            record_audit("risk.saved", f"Riesgo ({risk.level}, {risk.score}): {risk.description[:80]}", project)
            db.session.commit()
            flash("Riesgo guardado.", "success")
            return _back(project, "riesgos")
        except ValueError as error:
            _fail(error)
    return render_template("planning/risk_form.html", project=project, risk=risk, people=v.people(project.id))


@planning_bp.post("/<string:project_id>/risks/<string:risk_id>/delete")
@load_project
def delete_risk(project: Project, risk_id: str) -> Any:
    require_role("gestor")
    risk = _risk(project, risk_id)
    record_audit("risk.deleted", f"Riesgo eliminado: {risk.description[:80]}", project)
    db.session.delete(risk)
    db.session.commit()
    flash("Riesgo eliminado.", "success")
    return _back(project, "riesgos")
