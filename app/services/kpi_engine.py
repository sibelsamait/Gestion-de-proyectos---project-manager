"""Evaluador seguro y auditable de KPI."""

from decimal import Decimal, InvalidOperation

from simpleeval import (
    EvalWithCompoundTypes,
    FunctionNotDefined,
    NameNotDefined,
    SimpleEval,
)
from sqlalchemy.orm import Session

from ..models import KpiDefinition, KpiMeasurement

ALLOWED_VARIABLES = frozenset(
    {
        "trabajo_completado",
        "trabajo_total",
        "hitos_en_plazo",
        "hitos_vencidos",
        "costo_real",
        "costo_planificado",
        "tareas_atrasadas",
        "tareas_evaluadas",
        "horas_asignadas",
        "horas_disponibles",
        "cambios_aprobados",
        "cambios_totales",
    }
)
ALLOWED_FUNCTIONS = {"abs": abs, "min": min, "max": max, "round": round}


def _json_values(values: dict[str, Decimal | int | float]) -> dict[str, str | int | float]:
    """Convierte valores numéricos a una representación JSON estable."""
    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


class KpiError(ValueError):
    """Error de definición o evaluación de KPI."""


def _validate_definition(kpi: KpiDefinition) -> None:
    """Rechaza variables o fórmulas fuera de la lista blanca."""
    variables = set(kpi.variables or [])
    unknown = variables - ALLOWED_VARIABLES
    if unknown:
        raise KpiError(f"Variables no permitidas: {', '.join(sorted(unknown))}.")
    if not kpi.formula.strip():
        raise KpiError("La fórmula no puede estar vacía.")
    try:
        SimpleEval(functions=ALLOWED_FUNCTIONS).parse(kpi.formula)
    except (NameNotDefined, SyntaxError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise KpiError("La fórmula del KPI no es válida o usa nombres no declarados.") from exc


def evaluate_kpi(session: Session, kpi: KpiDefinition, values: dict[str, Decimal | int | float]) -> KpiMeasurement:
    """Evalúa, clasifica y guarda una medición histórica."""
    _validate_definition(kpi)
    missing = set(kpi.variables or []) - values.keys()
    if missing:
        raise KpiError(f"Faltan variables: {', '.join(sorted(missing))}.")
    evaluator = EvalWithCompoundTypes(functions=ALLOWED_FUNCTIONS)
    evaluator.names = {name: values[name] for name in kpi.variables}
    try:
        result = Decimal(str(evaluator.eval(kpi.formula)))
    except (
        InvalidOperation,
        FunctionNotDefined,
        NameNotDefined,
        SyntaxError,
        TypeError,
        ValueError,
        ZeroDivisionError,
    ) as exc:
        raise KpiError("No fue posible evaluar la fórmula del KPI.") from exc
    status = classify_result(result, kpi)
    kpi.result = result
    kpi.status = status
    measurement = KpiMeasurement(
        kpi_id=kpi.id,
        result=result,
        status=status,
        inputs=_json_values(values),
    )
    session.add(measurement)
    return measurement


def classify_result(result: Decimal, kpi: KpiDefinition) -> str:
    """Clasifica un resultado con umbrales configurables."""
    thresholds = kpi.thresholds or {}
    if kpi.direction == "range":
        low = Decimal(str(thresholds.get("min", kpi.target)))
        high = Decimal(str(thresholds.get("max", kpi.target)))
        return "green" if low <= result <= high else "red"
    green = Decimal(str(thresholds.get("green", kpi.target)))
    yellow = Decimal(str(thresholds.get("yellow", green)))
    if kpi.direction == "higher":
        return "green" if result >= green else "yellow" if result >= yellow else "red"
    return "green" if result <= green else "yellow" if result <= yellow else "red"
