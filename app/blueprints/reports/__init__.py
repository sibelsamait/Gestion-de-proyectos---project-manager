"""Exportación de informes PDF."""

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ...extensions import db
from ...services.currency import RateUnavailableError, validate_currency
from ...services.pdf_report import build_project_pdf
from ...services.project_overview import project_overview, resolve_money_context
from ..projects import load_project

reports_bp = Blueprint("reports", __name__)


@reports_bp.get("/projects/<string:project_id>/informe")
@load_project
def report_preview(project):
    """Muestra las secciones del informe y su completitud antes de exportar."""
    money, fallback = resolve_money_context(session.get("currency", "CLP"), db.session)
    return render_template(
        "reports/preview.html",
        project=project,
        overview=project_overview(db.session, project, money),
        currency_fallback=fallback,
    )


@reports_bp.get("/projects/<string:project_id>/export_pdf")
@load_project
def export_pdf(project):
    """Genera el PDF para cualquier rol del proyecto."""
    try:
        currency = validate_currency(request.args.get("currency"))
        document = build_project_pdf(db.session, project, currency)
    except (RateUnavailableError, ValueError) as error:
        flash(f"No fue posible generar el informe: {error}", "error")
        return redirect(url_for("reports.report_preview", project_id=project.id))
    return Response(
        document.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-{project.code}.pdf"'},
    )
