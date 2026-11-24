"""Cálculos de planificación y control: alcance, evaluación económica, valor ganado y riesgos."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    STUDY_TYPES,
    CashFlow,
    PreinvestmentStudy,
    Project,
    Resource,
    Risk,
    ScopeItem,
    Task,
    TaskResourceAssignment,
)
from .costs import assignment_cost

ZERO = Decimal(0)

# ------------------------------------------------------------- Plantillas de alcance

SCOPE_TEMPLATES: dict[str, dict] = {
    "software_a_medida": {
        "label": "Desarrollo de software a medida",
        "items": [
            ("requisito_funcional", "Gestión de usuarios con autenticación y perfiles de acceso.",
             "Cada perfil accede solo a las funciones autorizadas."),
            ("requisito_funcional", "Módulos de negocio definidos en el levantamiento de requisitos.",
             "Casos de uso aprobados por el cliente ejecutados sin errores críticos."),
            ("requisito_funcional", "Reportes operativos exportables.", "Reportes validados con datos reales."),
            ("requisito_no_funcional", "Tiempo de respuesta menor a 2 segundos en operaciones habituales.",
             "Prueba de carga con usuarios concurrentes estimados."),
            ("requisito_no_funcional", "Disponibilidad del 99 % en horario hábil.", None),
            ("entregable", "Documento de requisitos aprobado.", "Firma del patrocinador."),
            ("entregable", "Sistema desplegado en ambiente productivo.", "Acta de puesta en marcha."),
            ("entregable", "Manual de usuario y capacitación al equipo del cliente.", None),
            ("exclusion", "Adquisición de hardware y licencias de terceros.", None),
            ("exclusion", "Migración de datos históricos anteriores al proyecto.", None),
            ("exclusion", "Soporte y mantenimiento posterior al período de garantía.", None),
            ("supuesto", "El cliente asigna una contraparte con disponibilidad semanal.", None),
            ("restriccion", "Presupuesto y plazo según el documento de autorización.", None),
        ],
    },
    "aplicacion_movil": {
        "label": "Aplicación móvil",
        "items": [
            ("requisito_funcional", "Registro e inicio de sesión de usuarios.", None),
            ("requisito_funcional", "Funcionalidades principales definidas en el backlog priorizado.", None),
            ("requisito_funcional", "Notificaciones push.", None),
            ("requisito_no_funcional", "Compatibilidad con las dos últimas versiones de Android e iOS.", None),
            ("requisito_no_funcional", "Funcionamiento con conectividad intermitente.", None),
            ("entregable", "Aplicación publicada en App Store y Google Play.", "Aprobación de ambas tiendas."),
            ("entregable", "API de servicios documentada.", None),
            ("exclusion", "Versión web o de escritorio.", None),
            ("exclusion", "Costos de cuentas de desarrollador en las tiendas.", None),
            ("supuesto", "El cliente provee contenidos e imagen corporativa.", None),
            ("restriccion", "Cumplimiento de las políticas de publicación de cada tienda.", None),
        ],
    },
    "integracion_sistemas": {
        "label": "Integración de sistemas",
        "items": [
            ("requisito_funcional", "Intercambio de datos entre los sistemas definidos en el alcance.", None),
            ("requisito_funcional", "Registro y reintento de transacciones fallidas.", None),
            ("requisito_no_funcional", "Comunicación cifrada entre sistemas.", None),
            ("entregable", "Mapa de integración y contratos de interfaz.", None),
            ("entregable", "Integraciones en producción con monitoreo.", None),
            ("exclusion", "Modificaciones internas a los sistemas de terceros.", None),
            ("supuesto", "Los proveedores entregan acceso a ambientes de prueba.", None),
            ("restriccion", "Ventanas de despliegue acordadas con operaciones.", None),
        ],
    },
}


def apply_scope_template(session: Session, project_id: str, template_key: str) -> int:
    """Agrega los elementos de la plantilla que aún no existen; devuelve cuántos se agregaron."""
    template = SCOPE_TEMPLATES.get(template_key)
    if template is None:
        raise ValueError("La plantilla de alcance no existe.")
    existing = {
        (item.category, item.description)
        for item in session.scalars(select(ScopeItem).where(ScopeItem.project_id == project_id))
    }
    position = len(existing)
    added = 0
    for category, description, criteria in template["items"]:
        if (category, description) in existing:
            continue
        position += 1
        session.add(ScopeItem(project_id=project_id, category=category, description=description,
                              acceptance_criteria=criteria, position=position))
        added += 1
    return added


# ------------------------------------------------------------ Evaluación económica

def npv(rate: Decimal, flows: list[Decimal]) -> Decimal:
    """Valor actual neto: Σ flujo_t / (1 + r)^t, con t desde 0."""
    factor = 1 + rate
    return sum((flow / factor**period for period, flow in enumerate(flows)), ZERO)


def irr(flows: list[Decimal]) -> Decimal | None:
    """Tasa interna de retorno por bisección; None si los flujos no cambian de signo."""
    if not any(flow < 0 for flow in flows) or not any(flow > 0 for flow in flows):
        return None
    low, high = Decimal("-0.99"), Decimal(10)
    if npv(low, flows) * npv(high, flows) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        value = npv(mid, flows)
        if abs(value) < Decimal("0.0001"):
            break
        if npv(low, flows) * value < 0:
            high = mid
        else:
            low = mid
    return mid


def payback(flows: list[Decimal], rate: Decimal | None = None) -> Decimal | None:
    """Período de recuperación (descontado si se indica tasa), con interpolación lineal."""
    accumulated = ZERO
    for period, flow in enumerate(flows):
        value = flow / (1 + rate) ** period if rate is not None else flow
        previous = accumulated
        accumulated += value
        if period > 0 and previous < 0 <= accumulated:
            return Decimal(period - 1) + (-previous / value)
    return None


@dataclass
class Evaluation:
    """Resultado de la evaluación económica del proyecto."""

    rows: list[dict]
    rate: Decimal
    npv: Decimal | None
    irr: Decimal | None
    payback: Decimal | None
    discounted_payback: Decimal | None
    benefit_cost: Decimal | None
    total_investment: Decimal

    @property
    def has_data(self) -> bool:
        return any(row["net"] != 0 for row in self.rows)

    @property
    def verdict(self) -> str:
        if not self.has_data or self.npv is None:
            return "Sin flujos proyectados: registre inversión, ingresos y costos por período."
        if self.npv > 0:
            return ("El proyecto es rentable a la tasa exigida: genera valor por sobre la rentabilidad mínima "
                    "esperada por los inversionistas.")
        if self.npv == 0:
            return "El proyecto recupera exactamente la rentabilidad exigida."
        return "El proyecto no alcanza la rentabilidad exigida con los flujos proyectados."


def evaluate(session: Session, project: Project) -> Evaluation:
    """Flujo de caja por período e indicadores VAN, TIR, PRI y B/C."""
    stored = {
        flow.period: flow
        for flow in session.scalars(select(CashFlow).where(CashFlow.project_id == project.id))
    }
    rate = Decimal(project.discount_rate or 0) / 100
    rows = []
    for period in range(project.evaluation_years + 1):
        flow = stored.get(period)
        investment = flow.investment if flow else ZERO
        income = flow.income if flow else ZERO
        costs = flow.costs if flow else ZERO
        net = income - costs - investment
        rows.append({
            "period": period, "investment": investment, "income": income, "costs": costs, "net": net,
            "discounted": net / (1 + rate) ** period,
        })
    nets = [row["net"] for row in rows]
    has_data = any(nets)
    outflows = sum(((row["investment"] + row["costs"]) / (1 + rate) ** row["period"] for row in rows), ZERO)
    inflows = sum((row["income"] / (1 + rate) ** row["period"] for row in rows), ZERO)
    return Evaluation(
        rows=rows,
        rate=rate,
        npv=npv(rate, nets) if has_data else None,
        irr=irr(nets) if has_data else None,
        payback=payback(nets) if has_data else None,
        discounted_payback=payback(nets, rate) if has_data else None,
        benefit_cost=(inflows / outflows) if outflows else None,
        total_investment=sum((row["investment"] for row in rows), ZERO),
    )


def studies(session: Session, project_id: str) -> list[PreinvestmentStudy]:
    """Los cinco estudios de preinversión, existan o no en la base (orden fijo)."""
    stored = {
        study.study_type: study
        for study in session.scalars(
            select(PreinvestmentStudy).where(PreinvestmentStudy.project_id == project_id)
        )
    }
    return [
        stored.get(kind) or PreinvestmentStudy(project_id=project_id, study_type=kind, status="pendiente")
        for kind in STUDY_TYPES
    ]


def authorization_gaps(project: Project) -> list[str]:
    """Lo que falta en el documento de autorización para pasar a la etapa de inversión."""
    gaps = []
    if not project.authorized_by:
        gaps.append("Indique quién autoriza el proyecto.")
    if not project.authorization_date:
        gaps.append("Registre la fecha de autorización.")
    if not project.authorization_reference:
        gaps.append("Registre el número o enlace del documento de autorización.")
    if not project.director_id:
        gaps.append("Designe al Director(a) del proyecto.")
    if not project.authorized_budget:
        gaps.append("Defina el presupuesto autorizado.")
    return gaps


# ---------------------------------------------------------------- Valor ganado

@dataclass
class EarnedValue:
    """Indicadores de valor ganado a la fecha de corte (montos en CLP)."""

    bac: Decimal
    pv: Decimal
    ev: Decimal
    ac: Decimal

    @property
    def cpi(self) -> Decimal | None:
        return self.ev / self.ac if self.ac else None

    @property
    def spi(self) -> Decimal | None:
        return self.ev / self.pv if self.pv else None

    @property
    def cv(self) -> Decimal:
        return self.ev - self.ac

    @property
    def sv(self) -> Decimal:
        return self.ev - self.pv

    @property
    def eac(self) -> Decimal | None:
        return self.bac / self.cpi if self.cpi else None

    @property
    def has_data(self) -> bool:
        return self.bac > 0


def task_costs(session: Session, project_id: str) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Costo planificado y real por tarea según sus asignaciones de recursos (CLP)."""
    planned: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    for assignment, resource in session.execute(
        select(TaskResourceAssignment, Resource)
        .join(Resource, Resource.id == TaskResourceAssignment.resource_id)
        .where(Resource.project_id == project_id)
    ):
        planned[assignment.task_id] = planned.get(assignment.task_id, ZERO) + assignment_cost(
            resource, assignment.planned_units
        )
        actual[assignment.task_id] = actual.get(assignment.task_id, ZERO) + assignment_cost(
            resource, assignment.actual_units
        )
    return planned, actual


def planned_fraction(task: Task, today: date) -> Decimal:
    """Fracción del trabajo que debería estar hecha hoy según el calendario planificado."""
    if not task.planned_start or not task.planned_end:
        return ZERO
    if today < task.planned_start:
        return ZERO
    if today >= task.planned_end:
        return Decimal(1)
    total = (task.planned_end - task.planned_start).days + 1
    return Decimal((today - task.planned_start).days + 1) / Decimal(total)


def earned_value(tasks: list[Task], planned: dict[str, Decimal], actual: dict[str, Decimal],
                 today: date | None = None) -> EarnedValue:
    """BAC, PV, EV y AC del conjunto de tareas."""
    today = today or date.today()
    bac = pv = ev = ac = ZERO
    for task in tasks:
        cost = planned.get(task.id, ZERO)
        bac += cost
        pv += cost * planned_fraction(task, today)
        ev += cost * Decimal(task.progress_percent) / 100
        ac += actual.get(task.id, ZERO)
    return EarnedValue(bac=bac, pv=pv, ev=ev, ac=ac)


# -------------------------------------------------------------------- Riesgos

def risk_matrix(risks: list[Risk]) -> list[list[list[Risk]]]:
    """Matriz 5×5 [impacto 5→1][probabilidad 1→5] con los riesgos abiertos de cada celda."""
    matrix = [[[] for _ in range(5)] for _ in range(5)]
    for risk in risks:
        if risk.status in ("cerrado",):
            continue
        matrix[5 - risk.impact][risk.probability - 1].append(risk)
    return matrix
