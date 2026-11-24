"""Informe PDF completo del proyecto, generado en memoria.

Los capítulos siguen el ciclo del proyecto (preinversión → autorización → planificación →
control) y usan los mismos datos que la interfaz (`project_overview`), de modo que la vista
previa del informe y el documento nunca difieren.
"""

from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models import Project
from ..ui import (
    PROJECT_ROLE_INFO,
    RISK_RESPONSE_LABELS,
    SCOPE_CATEGORY_LABELS,
    STUDY_TYPE_LABELS,
    date_cl,
    label_for,
    number_cl,
)
from .currency import RateUnavailableError, currency_context, format_money
from .project_overview import project_overview

PRIMARY = colors.HexColor("#0F4C81")
TEXT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
GRID = colors.HexColor("#E2E8F0")
ZEBRA = colors.HexColor("#F8FAFC")

CHAPTERS = (
    "Fundamentación y objetivos",
    "Organización y autorización",
    "Estudios de preinversión y evaluación económica",
    "Alcance del proyecto",
    "Planificación temporal y presupuestaria",
    "Control de costos y plazo",
    "Gestión de riesgos",
    "Indicadores (KPI)",
    "Gestión del cambio",
    "Conclusiones",
)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13.5, textColor=TEXT)
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, leading=24, textColor=PRIMARY,
                                alignment=0, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", parent=body, textColor=MUTED, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=14, leading=18, textColor=PRIMARY,
                             spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11, leading=14, textColor=TEXT,
                             spaceBefore=8, spaceAfter=4),
        "body": body,
        "muted": ParagraphStyle("muted", parent=body, textColor=MUTED, fontSize=8.5, leading=11),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11),
        "cell_head": ParagraphStyle("cell_head", parent=body, fontSize=8.5, leading=11, textColor=colors.white,
                                    fontName="Helvetica-Bold"),
    }


def _p(text, style) -> Paragraph:
    """Párrafo con el texto escapado (los datos provienen de usuarios)."""
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _table(header: list[str], rows: list[list], st: dict, widths: list[float] | None = None) -> Table:
    """Tabla corporativa con encabezado azul, filas alternadas y celdas que ajustan texto."""
    data = [[_p(cell, st["cell_head"]) for cell in header]]
    data += [[cell if isinstance(cell, Paragraph) else _p(cell, st["cell"]) for cell in row] for row in rows]
    if not rows:
        data.append([_p("Sin registros.", st["muted"])] + [""] * (len(header) - 1))
    table = Table(data, repeatRows=1, colWidths=widths)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("GRID", (0, 0), (-1, -1), 0.25, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    if not rows:
        style.append(("SPAN", (0, 1), (-1, 1)))
    table.setStyle(TableStyle(style))
    return table


def _key_values(pairs: list[tuple[str, str]], st: dict) -> Table:
    table = Table([[_p(k, st["muted"]), _p(v, st["body"])] for k, v in pairs], colWidths=[5 * cm, 13 * cm])
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _rate_footer(session) -> str:
    """Leyenda de tasas sin impedir un informe CLP sin histórico."""
    labels = []
    for indicator in ("UF", "USD"):
        try:
            rate = currency_context(indicator, session=session)
        except RateUnavailableError:
            labels.append(f"{indicator} no disponible")
        else:
            labels.append(f"{indicator} = {format_money(rate['rate_used'], 'CLP')} ({rate['rate_date_display']})")
    return " · ".join(labels)


def _pct(value) -> str:
    return "—" if value is None else f"{number_cl(value * 100, 1)} %"


def _num(value, decimals=2) -> str:
    return "—" if value is None else number_cl(value, decimals)


def build_project_pdf(session, project: Project, currency: str = "CLP") -> BytesIO:
    """Construye el informe completo sin crear archivos temporales."""
    money = currency_context(currency, session=session)
    o = project_overview(session, project, money)
    fmt, st = o["fmt"], _styles()
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=1.6 * cm, leftMargin=1.6 * cm, topMargin=1.6 * cm,
        bottomMargin=1.8 * cm, title=f"Informe {project.code}", author="Gestión de proyectos",
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.6 * cm, 1 * cm, f"{project.code} · {project.name} · Informe generado el {date_cl(date.today())}")
        canvas.drawRightString(A4[0] - 1.6 * cm, 1 * cm, f"Página {doc.page}")
        canvas.restoreState()

    ev, evm, counts = o["evaluation"], o["evm"], o["counts"]
    phase = label_for("project_phase", project.phase)[0]
    status = label_for("project_status", project.status)[0]
    story = [
        _p(project.name, st["title"]),
        _p(f"Informe completo del proyecto · {project.code} · Etapa: {phase} · Estado: {status} · "
           f"Moneda: {currency}", st["subtitle"]),
        _p("Resumen ejecutivo", st["h1"]),
        _key_values([
            ("Patrocinador", project.sponsor or "—"),
            ("Director(a) del proyecto", o["director"] or "Sin designar"),
            ("Período planificado", f"{date_cl(project.planned_start)} a {date_cl(project.planned_end)}"),
            ("Presupuesto autorizado", fmt(project.authorized_budget)),
            ("Avance promedio", (f"{number_cl(o['tracking']['progress'], 1)} % "
                                f"({counts['tasks_done']} de {counts['tasks']} tareas completadas; "
                                f"{counts['tasks_overdue']} atrasadas)")),
            ("Evaluación económica", f"VAN {fmt(ev.npv) if ev.npv is not None else '—'} · TIR {_pct(ev.irr)}"),
            ("Riesgos altos o críticos abiertos", str(len(o["risks_open_high"]))),
            ("Solicitudes de cambio", str(counts["changes"])),
        ], st),
        _p("Contenido", st["h2"]),
        Paragraph("<br/>".join(f"{i}. {escape(title)}" for i, title in enumerate(CHAPTERS, start=1)), st["body"]),
    ]

    # 1. Fundamentación y objetivos
    story += [
        PageBreak(), _p(f"1. {CHAPTERS[0]}", st["h1"]),
        _p("Descripción", st["h2"]), _p(project.description or "Sin descripción registrada.", st["body"]),
        _p("Objetivos", st["h2"]), _p(project.objectives or "Sin objetivos registrados.", st["body"]),
    ]

    # 2. Organización y autorización
    story += [
        _p(f"2. {CHAPTERS[1]}", st["h1"]),
        _p("Documento de autorización", st["h2"]),
        _key_values([
            ("Autorizado por", project.authorized_by or "Pendiente"),
            ("Fecha de autorización", date_cl(project.authorization_date)),
            ("Documento", project.authorization_reference or "Pendiente"),
            ("Director(a) designado(a)", o["director"] or "Sin designar"),
            ("Observaciones", project.authorization_notes or "—"),
        ], st),
        _p("Roles directivos", st["h2"]),
        _table(["Rol", "Personas", "Responsabilidad"], [
            [PROJECT_ROLE_INFO["admin"][0], ", ".join(o["managers"]) or "—", PROJECT_ROLE_INFO["admin"][1]],
            [PROJECT_ROLE_INFO["gestor"][0], ", ".join(o["leads"]) or "—", PROJECT_ROLE_INFO["gestor"][1]],
        ], st, [3.5 * cm, 4.5 * cm, 10 * cm]),
        _p("Estrategia de monitoreo y control", st["h2"]),
        _p(project.control_plan or "No definida.", st["body"]),
    ]

    # 3. Estudios y evaluación económica
    story += [
        PageBreak(), _p(f"3. {CHAPTERS[2]}", st["h1"]),
        _p("Estudios previos que sustentan la viabilidad del proyecto ante inversionistas y entidades "
           "financieras.", st["muted"]),
        _table(["Estudio", "Estado", "Conclusión"], [
            [STUDY_TYPE_LABELS[s.study_type][0], label_for("study_status", s.status)[0], s.conclusion or "—"]
            for s in o["studies"]
        ], st, [4 * cm, 2.5 * cm, 11.5 * cm]),
        _p("Flujo de caja proyectado", st["h2"]),
        _table(["Año", "Inversión", "Ingresos", "Costos", "Flujo neto", "Flujo descontado"], [
            [str(r["period"]), fmt(r["investment"]), fmt(r["income"]), fmt(r["costs"]), fmt(r["net"]),
             fmt(r["discounted"])] for r in ev.rows
        ], st),
        _p("Indicadores de rentabilidad", st["h2"]),
        _key_values([
            ("Tasa de descuento", f"{number_cl(project.discount_rate, 1)} % anual"),
            ("Valor actual neto (VAN)", fmt(ev.npv) if ev.npv is not None else "—"),
            ("Tasa interna de retorno (TIR)", _pct(ev.irr)),
            ("Período de recuperación", f"{_num(ev.payback, 1)} años (descontado: {_num(ev.discounted_payback, 1)})"),
            ("Relación beneficio/costo", _num(ev.benefit_cost)),
            ("Conclusión", ev.verdict),
        ], st),
    ]

    # 4. Alcance
    story += [PageBreak(), _p(f"4. {CHAPTERS[3]}", st["h1"])]
    for category, (label, inclusion) in SCOPE_CATEGORY_LABELS.items():
        items = o["scope"][category]
        tag = {"incluido": "incluido", "excluido": "excluido", "condicion": "condición"}[inclusion]
        story.append(_p(f"{label} ({tag})", st["h2"]))
        story.append(_table(["N.º", "Descripción", "Criterio de aceptación"], [
            [str(i), item.description, item.acceptance_criteria or "—"] for i, item in enumerate(items, start=1)
        ], st, [1.2 * cm, 9.8 * cm, 7 * cm]))

    # 5. Planificación
    story += [
        PageBreak(), _p(f"5. {CHAPTERS[4]}", st["h1"]),
        _p("Cronograma de tareas", st["h2"]),
        _table(["Tarea", "Responsable", "Inicio", "Término", "Avance", "Costo plan."], [
            [row["task"].name, row["responsible"] or "—", date_cl(row["task"].planned_start),
             date_cl(row["task"].planned_end), f"{number_cl(row['task'].progress_percent, 0)} %",
             format_money(row["planned_cost"], currency)] for row in o["tasks"]
        ], st, [5.4 * cm, 3 * cm, 2.1 * cm, 2.1 * cm, 1.6 * cm, 3.8 * cm]),
        _p("Hitos", st["h2"]),
        _table(["Hito", "Comprometida", "Real", "Estado"], [
            [row["milestone"].name, date_cl(row["milestone"].committed_date), date_cl(row["milestone"].actual_date),
             label_for("milestone_status", row["milestone"].status)[0]] for row in o["milestones"]
        ], st),
        _p("Presupuesto", st["h2"]),
        _key_values([
            ("Presupuesto autorizado", fmt(project.authorized_budget)),
            ("Costo planificado (recursos asignados)", format_money(o["planned_cost"], currency)),
            ("Uso del presupuesto", f"{number_cl(o['budget_usage'], 1)} %" if o["budget_usage"] is not None else "—"),
        ] + [(f"Costo {k.lower()}", format_money(v, currency)) for k, v in sorted(o["costs_by_category"].items())], st),
        _p(f"Tasas de referencia: {_rate_footer(session)}", st["muted"]),
    ]

    # 6. Control (valor ganado)
    story += [_p(f"6. {CHAPTERS[5]}", st["h1"])]
    if evm.has_data:
        story += [
            _table(["Indicador", "Valor", "Interpretación"], [
                ["Presupuesto de las tareas (BAC)", fmt(evm.bac), "Costo total planificado"],
                ["Valor planificado (PV)", fmt(evm.pv), "Trabajo que debía estar hecho a la fecha"],
                ["Valor ganado (EV)", fmt(evm.ev), "Trabajo realizado, valorizado"],
                ["Costo real (AC)", fmt(evm.ac), "Gasto efectivo registrado"],
                ["Índice de costo (CPI)", _num(evm.cpi), "≥ 1: dentro de presupuesto; < 1: sobrecosto"],
                ["Índice de plazo (SPI)", _num(evm.spi), "≥ 1: en plazo o adelantado; < 1: atraso"],
                ["Variación de costo (CV)", fmt(evm.cv), "EV − AC"],
                ["Variación de plazo (SV)", fmt(evm.sv), "EV − PV"],
                ["Estimación al término (EAC)", fmt(evm.eac) if evm.eac is not None else "—", "BAC ÷ CPI"],
            ], st, [5.5 * cm, 4 * cm, 8.5 * cm]),
        ]
    else:
        story.append(_p("Sin asignaciones de recursos a tareas: no es posible medir el valor ganado.", st["body"]))

    # 7. Riesgos
    story += [
        _p(f"7. {CHAPTERS[6]}", st["h1"]),
        _table(["Riesgo", "P", "I", "Nivel", "Respuesta", "Estado"], [
            [Paragraph(f"{escape(r.description)}"
                       + (f"<br/><font color='#64748B'>Plan: {escape(r.response_plan)}</font>" if r.response_plan else ""),
                       st["cell"]),
             str(r.probability), str(r.impact), f"{label_for('risk_level', r.level)[0]} ({r.score})",
             RISK_RESPONSE_LABELS[r.response], label_for("risk_status", r.status)[0]]
            for r in o["risks"]
        ], st, [8 * cm, 0.8 * cm, 0.8 * cm, 2.6 * cm, 2.4 * cm, 3.4 * cm]),
    ]

    # 8. KPI
    story += [
        _p(f"8. {CHAPTERS[7]}", st["h1"]),
        _table(["Código", "Indicador", "Meta", "Resultado", "Estado"], [
            [k.code, k.name, _num(k.target), _num(k.result), label_for("kpi_status", k.status)[0]]
            for k in o["kpis"]
        ], st),
    ]

    # 9. Cambios
    story += [
        _p(f"9. {CHAPTERS[8]}", st["h1"]),
        _table(["Solicitud", "Etapa", "Estado", "Costo estimado", "Costo real"], [
            [row["change"].change_code, row["change"].stage, label_for("change_status", row["change"].status)[0],
             format_money(row["estimated_cost"], currency), format_money(row["actual_cost"], currency)]
            for row in o["changes"]
        ], st),
    ]

    # 10. Conclusiones
    pending = [s for s in o["report"]["sections"] if s["status"] == "warn"]
    conclusions = [
        f"El proyecto se encuentra en la etapa de {phase.lower()} con estado «{status.lower()}».",
        ev.verdict,
        (f"El desempeño de costo (CPI {_num(evm.cpi)}) y de plazo (SPI {_num(evm.spi)}) se mide con las asignaciones "
         "registradas." if evm.has_data else "Aún no se registran asignaciones de recursos para medir el desempeño."),
        (f"Se mantienen {len(o['risks_open_high'])} riesgo(s) alto(s) o crítico(s) abiertos que requieren seguimiento."
         if o["risks_open_high"] else "No hay riesgos altos o críticos abiertos."),
    ]
    if pending:
        conclusions.append("Secciones con información incompleta: " + ", ".join(s["title"] for s in pending) + ".")
    story += [
        _p(f"10. {CHAPTERS[9]}", st["h1"]),
        KeepTogether([_p(f"• {line}", st["body"]) for line in conclusions]),
        Spacer(1, 0.4 * cm),
        _p(f"Montos expresados en {currency} con tasas a la fecha de generación ({money['rate_date_display']}). "
           "Este informe refleja los datos registrados al momento de la exportación.", st["muted"]),
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
