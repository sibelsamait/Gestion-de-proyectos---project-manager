"""Etiquetas, tonos y filtros de presentación compartidos por las plantillas."""

from datetime import date
from decimal import Decimal

from flask import Flask

# Cada catálogo asocia el valor persistido con (etiqueta, tono visual).
PROJECT_STATUS = {
    "planificado": ("Planificado", "neutral"),
    "en_ejecucion": ("En ejecución", "info"),
    "suspendido": ("Suspendido", "warning"),
    "terminado": ("Terminado", "success"),
}
MILESTONE_STATUS = {
    "pendiente": ("Pendiente", "neutral"),
    "en_progreso": ("En progreso", "info"),
    "cumplido": ("Cumplido", "success"),
    "vencido": ("Vencido", "danger"),
}
TASK_STATE = {
    "completada": ("Completada", "success"),
    "atrasada": ("Atrasada", "danger"),
    "en_curso": ("En curso", "info"),
    "no_iniciada": ("No iniciada", "neutral"),
}
CHANGE_STATUS = {
    "pending": ("Pendiente", "neutral"),
    "approved": ("Aprobado", "success"),
    "rejected": ("Rechazado", "danger"),
}
KPI_STATUS = {
    "green": ("En meta", "success"),
    "yellow": ("En observación", "warning"),
    "red": ("Fuera de meta", "danger"),
    "pending": ("Sin medición", "neutral"),
}
RISK = {
    "bajo": ("Bajo", "neutral"),
    "medio": ("Medio", "info"),
    "alto": ("Alto", "warning"),
    "critico": ("Crítico", "danger"),
}
PRIORITY = {
    "baja": ("Baja", "neutral"),
    "media": ("Media", "info"),
    "alta": ("Alta", "warning"),
    "critica": ("Crítica", "danger"),
}
KPI_SCOPE = {"project": "Proyecto", "task": "Tarea", "milestone": "Hito", "change": "Cambio"}
KPI_DIRECTION = {"higher": "Mayor es mejor", "lower": "Menor es mejor", "range": "Dentro de rango"}
# Roles por proyecto: (etiqueta, permisos), en el orden en que se ofrecen.
PROJECT_ROLE_INFO = {
    "admin": (
        "Gerente de proyecto",
        (
            "Monitorea el proyecto en su conjunto: preinversión y autorización, alcance, presupuesto y "
            "recursos, aprobación de cambios, organización y lista de usuarios."
        ),
    ),
    "gestor": (
        "Jefe de proyecto",
        (
            "Trabaja con el equipo técnico en la ejecución: tareas, hitos, dependencias, "
            "asignación de recursos, riesgos y mediciones de KPI."
        ),
    ),
    "miembro": ("Miembro", "Solo lectura y exportación del informe PDF; p. ej., el cliente del proyecto."),
}
DEFAULT_PROJECT_ROLE = "miembro"
PROJECT_PHASE = {
    "preinversion": ("Preinversión", "warning"),
    "inversion": ("Inversión", "success"),
}
STUDY_STATUS = {
    "pendiente": ("Pendiente", "neutral"),
    "en_curso": ("En curso", "info"),
    "completado": ("Completado", "success"),
}
RISK_LEVEL = {
    "bajo": ("Bajo", "neutral"),
    "medio": ("Medio", "info"),
    "alto": ("Alto", "warning"),
    "critico": ("Crítico", "danger"),
}
RISK_STATUS = {
    "identificado": ("Identificado", "neutral"),
    "en_tratamiento": ("En tratamiento", "info"),
    "cerrado": ("Cerrado", "success"),
    "materializado": ("Materializado", "danger"),
}
STUDY_TYPE_LABELS = {
    "mercado": ("Estudio de mercado", "Demanda, oferta, precios y clientes objetivo que justifican el proyecto."),
    "tecnico": ("Estudio técnico", "Tecnología, arquitectura, infraestructura y capacidades requeridas."),
    "organizacional": ("Estudio organizacional", "Estructura, roles y costos administrativos del proyecto."),
    "legal": ("Estudio legal", "Normativa, licencias, protección de datos y contratos aplicables."),
    "financiero": ("Estudio financiero", "Inversión, ingresos, costos y rentabilidad del proyecto."),
}
SCOPE_CATEGORY_LABELS = {
    "requisito_funcional": ("Requisitos funcionales", "incluido"),
    "requisito_no_funcional": ("Requisitos no funcionales", "incluido"),
    "entregable": ("Entregables", "incluido"),
    "exclusion": ("Exclusiones", "excluido"),
    "supuesto": ("Supuestos", "condicion"),
    "restriccion": ("Restricciones", "condicion"),
}
RISK_RESPONSE_LABELS = {
    "evitar": "Evitar", "mitigar": "Mitigar", "transferir": "Transferir", "aceptar": "Aceptar",
}

REPORT_STATUS = {
    "ok": ("Completo", "success"),
    "warn": ("Revisar", "warning"),
    "empty": ("Sin datos", "neutral"),
    "auto": ("Automático", "info"),
}

CATALOGS = {
    "project_status": PROJECT_STATUS,
    "milestone_status": MILESTONE_STATUS,
    "task_state": TASK_STATE,
    "change_status": CHANGE_STATUS,
    "kpi_status": KPI_STATUS,
    "risk": RISK,
    "priority": PRIORITY,
    "report_status": REPORT_STATUS,
    "project_phase": PROJECT_PHASE,
    "study_status": STUDY_STATUS,
    "risk_level": RISK_LEVEL,
    "risk_status": RISK_STATUS,
}


def label_for(catalog: str, value: str | None) -> tuple[str, str]:
    """Devuelve (etiqueta, tono) y degrada a texto plano para valores desconocidos."""
    if value is None:
        return ("—", "neutral")
    entry = CATALOGS[catalog].get(value)
    if entry is None:
        return (value.replace("_", " ").capitalize(), "neutral")
    return entry


def date_cl(value: date | str | None) -> str:
    """Formatea fechas como DD-MM-AAAA, el formato usado en Chile."""
    if not value:
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d-%m-%Y")


def number_cl(value: Decimal | float | None, decimals: int = 0) -> str:
    """Formatea números con separadores es-CL."""
    if value is None:
        return "—"
    text = f"{Decimal(str(value)):,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def register_ui(app: Flask) -> None:
    """Registra filtros y globales de presentación."""
    app.add_template_global(label_for, "label_for")
    app.add_template_global(KPI_SCOPE, "KPI_SCOPE")
    app.add_template_global(KPI_DIRECTION, "KPI_DIRECTION")
    app.add_template_global(PROJECT_ROLE_INFO, "PROJECT_ROLE_INFO")
    for name in (
        "STUDY_TYPE_LABELS", "SCOPE_CATEGORY_LABELS", "RISK_RESPONSE_LABELS", "RISK_STATUS", "STUDY_STATUS",
    ):
        app.add_template_global(globals()[name], name)
    app.add_template_global(DEFAULT_PROJECT_ROLE, "DEFAULT_PROJECT_ROLE")
    app.add_template_global(PROJECT_STATUS, "PROJECT_STATUS")
    app.add_template_global(MILESTONE_STATUS, "MILESTONE_STATUS")
    app.add_template_filter(date_cl, "date_cl")
    app.add_template_filter(number_cl, "number_cl")
