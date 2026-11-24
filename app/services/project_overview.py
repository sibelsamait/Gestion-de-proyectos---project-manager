"""Modelos de vista para el portafolio, el detalle de proyecto y el informe PDF."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    SCOPE_CATEGORIES,
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    ProjectMember,
    Resource,
    Risk,
    ScopeItem,
    Task,
    TaskDependency,
    TaskResourceAssignment,
    User,
)
from .costs import assignment_cost
from .currency import (
    RateUnavailableError,
    convert_with_context,
    currency_context,
    format_money,
)
from .dashboard import tracking_dashboard
from .planning import (
    authorization_gaps,
    earned_value,
    evaluate,
    risk_matrix,
    studies,
    task_costs,
)

ZERO = Decimal(0)


def resolve_money_context(currency: str, session: Session) -> tuple[dict[str, Any], bool]:
    """Resuelve la moneda pedida; si no hay tasa, vuelve a CLP e informa el fallback."""
    try:
        return currency_context(currency, session=session), False
    except RateUnavailableError:
        return currency_context("CLP", session=session), currency != "CLP"


def task_state(task: Task, today: date | None = None) -> str:
    """Clasifica una tarea con las mismas reglas que el tablero de seguimiento."""
    today = today or date.today()
    if task.progress_percent >= 100:
        return "completada"
    if task.planned_end and task.planned_end < today:
        return "atrasada"
    if task.progress_percent > 0:
        return "en_curso"
    return "no_iniciada"


def _average_progress(tasks: list[Task]) -> float:
    return sum(float(task.progress_percent) for task in tasks) / len(tasks) if tasks else 0.0


def portfolio_rows(session: Session, projects: list[Project], money: dict[str, Any]) -> list[dict]:
    """Agrega avance, atrasos e hitos por proyecto en un número fijo de consultas."""
    ids = [project.id for project in projects]
    if not ids:
        return []
    tasks_by_project: defaultdict[str, list[Task]] = defaultdict(list)
    for task in session.scalars(select(Task).where(Task.project_id.in_(ids))):
        tasks_by_project[task.project_id].append(task)
    milestones_by_project: defaultdict[str, list[Milestone]] = defaultdict(list)
    for milestone in session.scalars(select(Milestone).where(Milestone.project_id.in_(ids))):
        milestones_by_project[milestone.project_id].append(milestone)
    director_ids = {project.director_id for project in projects if project.director_id}
    directors = {
        user.id: user.name
        for user in session.scalars(select(User).where(User.id.in_(director_ids)))
    } if director_ids else {}
    today = date.today()
    rows = []
    for project in projects:
        tasks = tasks_by_project[project.id]
        milestones = milestones_by_project[project.id]
        rows.append(
            {
                "project": project,
                "director": directors.get(project.director_id),
                "progress": _average_progress(tasks),
                "tasks_total": len(tasks),
                "tasks_overdue": sum(1 for task in tasks if task_state(task, today) == "atrasada"),
                "milestones_total": len(milestones),
                "milestones_done": sum(1 for item in milestones if item.status == "cumplido"),
                "budget": convert_with_context(project.authorized_budget, money),
            }
        )
    return rows


def project_overview(session: Session, project: Project, money: dict[str, Any]) -> dict[str, Any]:
    """Reúne todo lo que muestran el detalle del proyecto y la vista previa del informe."""
    today = date.today()
    member_rows = session.scalars(
        select(ProjectMember).where(ProjectMember.project_id == project.id).order_by(ProjectMember.added_at)
    ).all()
    registered = {
        user.email: user
        for user in session.scalars(select(User).where(User.email.in_([m.email for m in member_rows])))
    } if member_rows else {}
    names = {user.id: user.name for user in session.scalars(select(User))}

    tasks = session.scalars(
        select(Task)
        .where(Task.project_id == project.id)
        .order_by(Task.planned_start.is_(None), Task.planned_start, Task.name)
    ).all()
    task_names = {task.id: task.name for task in tasks}
    predecessors: defaultdict[str, list[dict]] = defaultdict(list)
    for dependency in session.scalars(
        select(TaskDependency).where(TaskDependency.successor_id.in_(list(task_names)))
    ) if task_names else []:
        predecessors[dependency.successor_id].append(
            {
                "name": task_names.get(dependency.predecessor_id, "—"),
                "type": dependency.dependency_type,
                "lag": dependency.lag_days,
            }
        )

    resources = session.scalars(
        select(Resource).where(Resource.project_id == project.id).order_by(Resource.type, Resource.name)
    ).all()
    planned_by_task: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for assignment, resource in session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(Resource.project_id == project.id)
    ):
        planned_by_task[assignment.task_id] += assignment_cost(resource, assignment.planned_units)

    task_rows = [
        {
            "task": task,
            "state": task_state(task, today),
            "responsible": names.get(task.responsible_id),
            "predecessors": predecessors.get(task.id, []),
            "planned_cost": convert_with_context(planned_by_task[task.id], money),
        }
        for task in tasks
    ]
    resource_rows = [
        {
            "resource": resource,
            "hourly_rate": convert_with_context(resource.hourly_rate, money),
            "unit_cost": convert_with_context(resource.unit_cost, money),
            "base_cost": convert_with_context(assignment_cost(resource, Decimal(1)), money),
        }
        for resource in resources
    ]
    milestones = session.scalars(
        select(Milestone)
        .where(Milestone.project_id == project.id)
        .order_by(Milestone.committed_date.is_(None), Milestone.committed_date)
    ).all()
    milestone_rows = [
        {"milestone": milestone, "responsible": names.get(milestone.responsible_id)}
        for milestone in milestones
    ]
    kpis = session.scalars(
        select(KpiDefinition).where(KpiDefinition.project_id == project.id).order_by(KpiDefinition.code)
    ).all()
    changes = session.scalars(
        select(ChangeRequest)
        .where(ChangeRequest.project_id == project.id)
        .order_by(ChangeRequest.requested_at.desc(), ChangeRequest.change_code)
    ).all()
    change_rows = [
        {
            "change": change,
            "requester": names.get(change.requester_id),
            "estimated_cost": convert_with_context(change.estimated_cost, money),
            "actual_cost": convert_with_context(change.actual_cost, money),
            "approvable": change.stage == "Decisión" and change.status != "approved",
        }
        for change in changes
    ]

    tracking = tracking_dashboard(session, project, money["currency"])
    planned_cost_clp = sum(planned_by_task.values(), ZERO)
    overview = {
        "money": money,
        "members": [
            {"member": member, "user": registered.get(member.email), "role": member.role}
            for member in member_rows
        ],
        "director": names.get(project.director_id),
        "tasks": task_rows,
        "milestones": milestone_rows,
        "resources": resource_rows,
        "kpis": kpis,
        "changes": change_rows,
        "tracking": tracking,
        "costs_by_category": {key: Decimal(value) for key, value in tracking["costs_by_category"].items()},
        "budget": convert_with_context(project.authorized_budget, money),
        "planned_cost": convert_with_context(planned_cost_clp, money),
        "budget_usage": (
            float(planned_cost_clp / project.authorized_budget * 100) if project.authorized_budget else None
        ),
        "counts": {
            "tasks": len(tasks),
            "tasks_overdue": sum(1 for row in task_rows if row["state"] == "atrasada"),
            "tasks_done": sum(1 for row in task_rows if row["state"] == "completada"),
            "milestones": len(milestones),
            "milestones_done": sum(1 for item in milestones if item.status == "cumplido"),
            "milestones_overdue": sum(1 for item in milestones if item.status == "vencido"),
            "resources": len(resources),
            "kpis": len(kpis),
            "kpis_measured": sum(1 for kpi in kpis if kpi.result is not None),
            "changes": len(changes),
            "changes_pending": sum(1 for change in changes if change.status != "approved"),
        },
        "upcoming_milestones": [
            row for row in milestone_rows
            if row["milestone"].status not in {"cumplido"} and row["milestone"].committed_date
        ][:4],
    }
    overview["charts"] = chart_data(overview)
    overview.update(planning_overview(session, project, money, tasks))
    overview["names"] = names
    overview["report"] = report_sections(project, overview)
    return overview


TASK_STATE_ORDER = ("completada", "en_curso", "atrasada", "no_iniciada")


def planning_overview(session: Session, project: Project, money: dict[str, Any], tasks: list[Task]) -> dict:
    """Preinversión, alcance, riesgos y valor ganado del proyecto."""
    planned, actual = task_costs(session, project.id)
    scope_items = session.scalars(
        select(ScopeItem).where(ScopeItem.project_id == project.id).order_by(ScopeItem.position)
    ).all()
    scope: dict[str, list[ScopeItem]] = {category: [] for category in SCOPE_CATEGORIES}
    for item in scope_items:
        scope[item.category].append(item)
    risks = sorted(
        session.scalars(select(Risk).where(Risk.project_id == project.id)).all(),
        key=lambda risk: (risk.status in ("cerrado",), -risk.score),
    )
    members = session.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id)).all()
    users = {
        user.email: user
        for user in session.scalars(select(User).where(User.email.in_([m.email for m in members])))
    } if members else {}

    def people_with(role: str) -> list[str]:
        return [users[m.email].name if m.email in users else m.email for m in members if m.role == role]

    return {
        "phase": project.phase,
        "studies": studies(session, project.id),
        "evaluation": evaluate(session, project),
        "auth_gaps": authorization_gaps(project),
        "scope": scope,
        "scope_count": len(scope_items),
        "risks": risks,
        "risk_matrix": risk_matrix(risks),
        "risks_open_high": [r for r in risks if r.status not in ("cerrado",) and r.level in ("alto", "critico")],
        "evm": earned_value(tasks, planned, actual),
        "actual_cost": convert_with_context(sum(actual.values(), ZERO), money),
        "people": sorted(
            (users[m.email] for m in members if m.email in users and users[m.email].is_active),
            key=lambda user: user.name,
        ),
        "managers": people_with("admin"),
        "leads": people_with("gestor"),
        "fmt": lambda amount: format_money(convert_with_context(amount or ZERO, money), money["currency"]),
    }


def chart_data(overview: dict[str, Any]) -> dict[str, Any]:
    """Series listas para los gráficos del resumen (sin cálculos en la plantilla)."""
    rows = overview["tasks"]
    total = len(rows) or 1
    states = [
        {
            "key": key,
            "count": sum(1 for row in rows if row["state"] == key),
        }
        for key in TASK_STATE_ORDER
    ]
    for item in states:
        item["share"] = item["count"] / total * 100

    by_stage: dict[str, list[float]] = {}
    for row in rows:
        by_stage.setdefault(row["task"].etapa or "Sin etapa", []).append(float(row["task"].progress_percent))
    stages = [
        {"label": stage, "value": sum(values) / len(values), "count": len(values)}
        for stage, values in by_stage.items()
    ]

    costs = sorted(overview["costs_by_category"].items(), key=lambda pair: pair[1], reverse=True)
    top = costs[0][1] if costs and costs[0][1] > 0 else Decimal(1)
    return {
        "states": states,
        "stages": stages,
        "costs": [
            {"label": label, "value": value, "share": float(value / top * 100)} for label, value in costs
        ],
    }


def report_sections(project: Project, overview: dict[str, Any]) -> dict[str, Any]:
    """Describe cada capítulo del PDF y qué datos faltan para que quede completo.

    Debe mantenerse alineado con `services.pdf_report.build_project_pdf` (mismos capítulos).
    """
    counts = overview["counts"]
    tasks = [row["task"] for row in overview["tasks"]]
    evaluation = overview["evaluation"]
    studies_done = sum(1 for study in overview["studies"] if study.status == "completado")
    scope = overview["scope"]
    included = sum(len(scope[c]) for c in ("requisito_funcional", "requisito_no_funcional", "entregable"))

    def section(key, number, title, contents, status, summary, issues=(), tab=None):
        return {"key": key, "number": number, "title": title, "contents": contents, "status": status,
                "summary": summary, "issues": list(issues), "tab": tab}

    def state(issues, empty=False):
        return "empty" if empty else "warn" if issues else "ok"

    summary_issues = []
    if not project.authorized_budget:
        summary_issues.append("El presupuesto autorizado es cero.")
    if not project.planned_start or not project.planned_end:
        summary_issues.append("Faltan fechas planificadas del proyecto.")
    foundation = [msg for cond, msg in (
        (not project.description, "Falta la descripción del proyecto."),
        (not project.objectives, "Faltan los objetivos del proyecto."),
    ) if cond]
    organization = list(overview["auth_gaps"])
    if not project.control_plan:
        organization.append("Falta la estrategia de monitoreo y control.")
    if not overview["leads"]:
        organization.append("No hay jefe de proyecto en la lista de usuarios.")
    economics = []
    if studies_done < 5:
        economics.append(f"{5 - studies_done} estudio(s) de preinversión sin completar.")
    if not evaluation.has_data:
        economics.append("No hay flujos de caja proyectados.")
    scope_issues = [msg for cond, msg in (
        (included == 0, "No hay requisitos ni entregables incluidos."),
        (not scope["exclusion"], "No se han declarado exclusiones."),
    ) if cond]
    undated = sum(1 for task in tasks if not task.planned_start or not task.planned_end)
    planning = [msg for cond, msg in (
        (not tasks, "No hay tareas registradas."),
        (undated, f"{undated} tarea(s) sin fechas planificadas."),
        (sum(1 for row in overview["milestones"] if not row["milestone"].committed_date),
         "Hay hitos sin fecha comprometida."),
    ) if cond]
    control = [] if overview["evm"].has_data else ["Sin recursos asignados a tareas: no se mide el valor ganado."]
    risk_issues = [msg for cond, msg in (
        (not overview["risks"], "No hay riesgos identificados."),
        (any(r.response != "aceptar" and not r.response_plan for r in overview["risks_open_high"]),
         "Hay riesgos altos o críticos sin plan de respuesta."),
    ) if cond]
    kpi_pending = counts["kpis"] - counts["kpis_measured"]

    sections = [
        section("summary", "Portada", "Resumen ejecutivo",
                "Etapa, estado, presupuesto, avance, rentabilidad, riesgos y cambios.",
                state(summary_issues), f"Avance {overview['tracking']['progress']:.1f} % · "
                f"{counts['tasks_overdue']} tarea(s) atrasada(s)", summary_issues, "resumen"),
        section("foundation", "Capítulo 1", "Fundamentación y objetivos", "Descripción y objetivos del proyecto.",
                state(foundation), "Descripción y objetivos registrados" if not foundation
                else "Información incompleta", foundation, "resumen"),
        section("organization", "Capítulo 2", "Organización y autorización",
                "Documento de autorización, Director(a), gerente y jefe de proyecto, estrategia de control.",
                state(organization), "Proyecto autorizado" if project.phase == "inversion"
                else "En preinversión", organization, "preinversion"),
        section("economics", "Capítulo 3", "Estudios de preinversión y evaluación económica",
                "Estudios previos, flujo de caja, VAN, TIR, período de recuperación y beneficio/costo.",
                state(economics), f"{studies_done} de 5 estudios · VAN "
                f"{overview['fmt'](evaluation.npv) if evaluation.npv is not None else 'sin calcular'}",
                economics, "preinversion"),
        section("scope", "Capítulo 4", "Alcance del proyecto",
                "Requisitos y entregables incluidos, exclusiones, supuestos y restricciones.",
                state(scope_issues, empty=not overview["scope_count"]),
                f"{included} incluido(s) · {len(scope['exclusion'])} exclusión(es)",
                scope_issues or ([] if overview["scope_count"] else ["No hay alcance definido."]), "alcance"),
        section("planning", "Capítulo 5", "Planificación temporal y presupuestaria",
                "Cronograma de tareas, hitos, presupuesto y tasas de cambio.",
                state(planning, empty=not tasks), f"{counts['tasks']} tarea(s) · {counts['milestones']} hito(s)",
                planning, "tareas"),
        section("control", "Capítulo 6", "Control de costos y plazo",
                "Valor ganado: BAC, PV, EV, AC, CPI, SPI y estimación al término.",
                state(control, empty=bool(control)),
                "Indicadores de valor ganado calculados" if not control else "Sin datos de ejecución",
                control, "tareas"),
        section("risks", "Capítulo 7", "Gestión de riesgos",
                "Riesgos con probabilidad, impacto, nivel, respuesta y estado.",
                state(risk_issues, empty=not overview["risks"]),
                f"{len(overview['risks'])} riesgo(s) · {len(overview['risks_open_high'])} alto(s) o crítico(s)",
                risk_issues, "riesgos"),
        section("kpi", "Capítulo 8", "Indicadores (KPI)", "Código, nombre, meta, último resultado y estado.",
                "empty" if not counts["kpis"] else "warn" if kpi_pending else "ok",
                f"{counts['kpis_measured']} de {counts['kpis']} KPI con medición",
                [f"{kpi_pending} KPI sin medición registrada."] if counts["kpis"] and kpi_pending
                else [] if counts["kpis"] else ["No hay KPI definidos."], "kpi"),
        section("changes", "Capítulo 9", "Gestión del cambio",
                "Solicitudes de cambio con costo estimado y real.",
                "ok" if counts["changes"] else "empty", f"{counts['changes']} solicitud(es) registrada(s)",
                [] if counts["changes"] else ["El capítulo se emitirá sin solicitudes."], "cambios"),
        section("closing", "Capítulo 10", "Conclusiones",
                "Síntesis automática de etapa, rentabilidad, desempeño y riesgos.",
                "auto", "Se genera sin intervención"),
    ]
    ready = sum(1 for item in sections if item["status"] in {"ok", "auto"})
    return {"sections": sections, "ready": ready, "total": len(sections)}
