"""Exportación de informes PDF."""

from flask import Blueprint, Response

from ...extensions import db
from ...services.pdf_report import build_project_pdf
from ..projects import project_access_required

reports_bp = Blueprint("reports", __name__)


@reports_bp.get("/projects/<string:project_id>/export_pdf")
@project_access_required
def export_pdf(project):
    """Genera un PDF solo para miembros autorizados."""
    document = build_project_pdf(db.session, project)
    return Response(
        document.getvalue(),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-{project.code}.pdf"'},
    )
