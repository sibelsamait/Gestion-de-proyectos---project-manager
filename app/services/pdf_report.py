"""Generación de informes PDF en memoria."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models import ChangeRequest, KpiDefinition, Project, Task
from .dashboard import tracking_dashboard


def build_project_pdf(session, project: Project) -> BytesIO:
    """Construye el informe solicitado sin crear archivos temporales."""
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Informe {project.code}",
        author="Gestión de proyectos",
    )
    styles = getSampleStyleSheet()
    summary = tracking_dashboard(session, project)
    tasks = session.query(Task).filter_by(project_id=project.id).order_by(Task.planned_start).all()
    changes = session.query(ChangeRequest).filter_by(project_id=project.id).all()
    kpis = session.query(KpiDefinition).filter_by(project_id=project.id).all()
    story = [
        Paragraph(project.name, styles["Title"]),
        Paragraph(f"Código: {project.code} — Estado: {project.status}", styles["Normal"]),
        Spacer(1, 0.4 * cm),
        Paragraph("Resumen ejecutivo", styles["Heading1"]),
        Paragraph(
            f"Avance promedio: {summary['progress']:.2f}%. "
            f"Tareas atrasadas: {summary['task_counts']['overdue']}. "
            f"Cambios registrados: {len(changes)}.",
            styles["BodyText"],
        ),
        Paragraph("Capítulo 1 — Fundamentación y alcance", styles["Heading1"]),
        Paragraph(project.description or "Sin descripción registrada.", styles["BodyText"]),
        Paragraph("Capítulo 2 — Planificación temporal y presupuestaria", styles["Heading1"]),
    ]
    task_rows = [["Tarea", "Inicio", "Término", "Avance"]]
    task_rows.extend(
        [
            [
                task.name,
                task.planned_start.isoformat() if task.planned_start else "—",
                task.planned_end.isoformat() if task.planned_end else "—",
                f"{task.progress_percent}%",
            ]
            for task in tasks
        ]
    )
    task_table = Table(task_rows, repeatRows=1)
    task_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176b87")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(task_table)
    story.extend(
        [
            Paragraph("Gantt", styles["Heading2"]),
            Paragraph(
                "El cronograma se representa en esta tabla con fechas planificadas. "
                "Las barras visuales del Gantt están disponibles en la interfaz web.",
                styles["BodyText"],
            ),
            Paragraph("Capítulo 3 — KPI", styles["Heading1"]),
            Table(
                [["Código", "Nombre", "Resultado", "Estado"]]
                + [
                    [kpi.code, kpi.name, str(kpi.result or "—"), kpi.status]
                    for kpi in kpis
                ],
                repeatRows=1,
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#176b87")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ]
                ),
            ),
            Paragraph("Capítulo 4 — Gestión del cambio", styles["Heading1"]),
            Paragraph(f"Solicitudes registradas: {len(changes)}.", styles["BodyText"]),
            Paragraph("Capítulo 5 — Tableros y conclusiones", styles["Heading1"]),
            Paragraph(
                "Este informe resume los datos persistidos al momento de la exportación. "
                "Los gráficos cuentan con alternativas tabulares en la aplicación.",
                styles["BodyText"],
            ),
        ]
    )
    document.build(story)
    output.seek(0)
    return output
