"""Generación de informes PDF en memoria."""

from io import BytesIO

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
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

from ..models import (
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    Task,
    TaskDependency,
)
from .currency import (
    RateUnavailableError,
    convert_with_context,
    currency_context,
    format_money,
)
from .dashboard import tracking_dashboard


def _rate_footer(session) -> str:
    """Construye la leyenda de tasas sin impedir un informe CLP sin histórico."""
    labels = []
    for indicator in ("UF", "USD"):
        try:
            rate = currency_context(indicator, session=session)
        except RateUnavailableError:
            labels.append(f"{indicator} no disponible")
        else:
            labels.append(
                f"{indicator} = {format_money(rate['rate_used'], 'CLP')} "
                f"({rate['rate_date_display']})"
            )
    return " · ".join(labels)


def _gantt_drawing(tasks: list[Task], milestones: list[Milestone], dependencies: list[TaskDependency]) -> Drawing | None:
    """Dibuja el Gantt con barras, avance, hitos y flechas."""
    dated = [
        value
        for task in tasks
        for value in (task.planned_start, task.planned_end)
        if value
    ] + [milestone.committed_date for milestone in milestones if milestone.committed_date]
    if not dated:
        return None
    start, end = min(dated), max(dated)
    span = max(1, (end - start).days + 1)
    left, chart_width = 115, 360
    row_height = 22
    height = max(45, (len(tasks) + len(milestones)) * row_height + 25)
    drawing = Drawing(500, height)

    def x(day):
        return left + ((day - start).days / span) * chart_width

    task_positions: dict[str, tuple[float, float]] = {}
    y = height - 35
    for task in tasks:
        drawing.add(String(0, y + 4, task.name[:18], fontSize=7))
        if task.planned_start and task.planned_end:
            width = max(4, x(task.planned_end) - x(task.planned_start))
            drawing.add(Rect(x(task.planned_start), y, width, 10, fillColor=colors.HexColor("#b7c9d6"), strokeColor=None))
            progress_width = width * float(task.progress_percent or 0) / 100
            drawing.add(Rect(x(task.planned_start), y, progress_width, 10, fillColor=colors.HexColor("#176b87"), strokeColor=None))
            if task.actual_start and task.actual_end:
                drawing.add(
                    Rect(
                        x(task.actual_start),
                        y - 3,
                        max(3, x(task.actual_end) - x(task.actual_start)),
                        3,
                        fillColor=colors.HexColor("#e67e22"),
                        strokeColor=None,
                    )
                )
            task_positions[task.id] = (x(task.planned_start), y + 5)
        y -= row_height
    for milestone in milestones:
        if milestone.committed_date:
            center_x = x(milestone.committed_date)
            center_y = y + 5
            drawing.add(String(0, center_y + 2, milestone.name[:18], fontSize=7))
            drawing.add(
                Polygon(
                    [center_x, center_y + 7, center_x + 6, center_y, center_x, center_y - 7, center_x - 6, center_y],
                    fillColor=colors.HexColor("#d35400"),
                    strokeColor=None,
                )
            )
        y -= row_height
    for dependency in dependencies:
        predecessor = task_positions.get(dependency.predecessor_id)
        successor = task_positions.get(dependency.successor_id)
        if predecessor and successor:
            x1, y1 = predecessor
            x2, y2 = successor
            drawing.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#555555"), strokeWidth=0.7))
            drawing.add(
                Polygon(
                    [x2, y2, x2 - 4, y2 + 2, x2 - 4, y2 - 2],
                    fillColor=colors.HexColor("#555555"),
                    strokeColor=None,
                )
            )
    drawing.add(Line(left, height - 18, left + chart_width, height - 18, strokeColor=colors.grey))
    drawing.add(String(left, height - 12, start.isoformat(), fontSize=6))
    drawing.add(String(left + chart_width - 45, height - 12, end.isoformat(), fontSize=6))
    return drawing


def build_project_pdf(session, project: Project, currency: str = "CLP") -> BytesIO:
    """Construye el informe solicitado sin crear archivos temporales."""
    money_context = currency_context(currency, session=session)
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
    summary = tracking_dashboard(session, project, currency)
    tasks = session.query(Task).filter_by(project_id=project.id).order_by(Task.planned_start).all()
    milestones = session.query(Milestone).filter_by(project_id=project.id).all()
    dependencies = (
        session.query(TaskDependency)
        .join(Task, Task.id == TaskDependency.predecessor_id)
        .filter(Task.project_id == project.id)
        .all()
    )
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
            f"Cambios registrados: {len(changes)}. "
            f"Presupuesto autorizado: {format_money(convert_with_context(project.authorized_budget, money_context), currency)}.",
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
    story.append(Paragraph(_rate_footer(session), styles["BodyText"]))
    story.extend(
        [
            Paragraph("Gantt", styles["Heading2"]),
            _gantt_drawing(tasks, milestones, dependencies)
            or Paragraph("No hay fechas planificadas para dibujar el Gantt.", styles["BodyText"]),
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
            Table(
                [["Cambio", "Costo estimado", "Costo real"]]
                + [
                    [
                        change.change_code,
                        format_money(convert_with_context(change.estimated_cost, money_context), currency),
                        format_money(convert_with_context(change.actual_cost, money_context), currency),
                    ]
                    for change in changes
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
            Paragraph(f"Solicitudes registradas: {len(changes)}.", styles["BodyText"]),
            Paragraph(
                f"Moneda del informe: {currency}. "
                f"Las tasas corresponden a la fecha de generación ({money_context['rate_date_display']}).",
                styles["BodyText"],
            ),
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
