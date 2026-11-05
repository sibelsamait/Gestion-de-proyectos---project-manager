"""Motor de calendario hábil y dependencias de tareas."""

from collections import defaultdict, deque
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NonWorkingDay, Task, TaskDependency


class ScheduleError(ValueError):
    """Error de calendario que debe provocar rollback."""


def working_days(project_id: str, session: Session) -> set[date]:
    """Devuelve los feriados configurados para un proyecto."""
    return set(
        session.scalars(
            select(NonWorkingDay.day).where(NonWorkingDay.project_id == project_id)
        )
    )


def is_working_day(day: date, holidays: set[date]) -> bool:
    """Indica si una fecha es hábil de lunes a viernes."""
    return day.weekday() < 5 and day not in holidays


def add_working_days(day: date, amount: int, holidays: set[date]) -> date:
    """Suma días hábiles; admite desfases negativos."""
    step = 1 if amount >= 0 else -1
    remaining = abs(amount)
    result = day
    while remaining:
        result += timedelta(days=step)
        if is_working_day(result, holidays):
            remaining -= 1
    return result


def next_working_day(day: date, holidays: set[date]) -> date:
    """Busca el día hábil desde una fecha dada hacia adelante."""
    result = day
    while not is_working_day(result, holidays):
        result += timedelta(days=1)
    return result


def task_end(start: date, duration: int, holidays: set[date]) -> date:
    """Calcula término inclusivo para una duración hábil."""
    if duration < 1:
        return start
    return add_working_days(start, duration - 1, holidays)


def task_start(end: date, duration: int, holidays: set[date]) -> date:
    """Calcula inicio inclusivo retrocediendo una duración hábil."""
    if duration < 1:
        return end
    return add_working_days(end, -(duration - 1), holidays)


def topological_order(tasks: Iterable[Task], dependencies: Iterable[TaskDependency]) -> list[Task]:
    """Ordena tareas y rechaza ciclos mediante Kahn."""
    task_map = {task.id: task for task in tasks}
    successors: dict[str, list[str]] = defaultdict(list)
    indegree = {task_id: 0 for task_id in task_map}
    for dependency in dependencies:
        if dependency.predecessor_id not in task_map or dependency.successor_id not in task_map:
            raise ScheduleError("La dependencia referencia tareas de otro proyecto.")
        if dependency.predecessor_id == dependency.successor_id:
            raise ScheduleError("Una tarea no puede depender de sí misma.")
        successors[dependency.predecessor_id].append(dependency.successor_id)
        indegree[dependency.successor_id] += 1
    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    ordered: list[Task] = []
    while queue:
        task_id = queue.popleft()
        ordered.append(task_map[task_id])
        for successor_id in successors[task_id]:
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                queue.append(successor_id)
    if len(ordered) != len(task_map):
        raise ScheduleError("La dependencia crea un ciclo; no se guardaron cambios.")
    return ordered


def validate_dependency(session: Session, dependency: TaskDependency) -> None:
    """Valida pertenencia, tipo y ciclos antes de insertar una dependencia."""
    predecessor = session.get(Task, dependency.predecessor_id)
    successor = session.get(Task, dependency.successor_id)
    if not predecessor or not successor or predecessor.project_id != successor.project_id:
        raise ScheduleError("Las tareas deben pertenecer al mismo proyecto.")
    if dependency.dependency_type not in {"FS", "SS", "FF", "SF"}:
        raise ScheduleError("Tipo de dependencia inválido.")
    existing = list(
        session.scalars(
            select(TaskDependency).join(Task, Task.id == TaskDependency.predecessor_id).where(
                Task.project_id == predecessor.project_id
            )
        )
    )
    if any(
        item.predecessor_id == dependency.predecessor_id
        and item.successor_id == dependency.successor_id
        for item in existing
    ):
        raise ScheduleError("La dependencia ya existe.")
    topological_order(
        list(session.scalars(select(Task).where(Task.project_id == predecessor.project_id))),
        [*existing, dependency],
    )


def _constraint_start(
    predecessor: Task,
    successor: Task,
    dependency: TaskDependency,
    holidays: set[date],
) -> date | None:
    """Obtiene el inicio mínimo que impone una dependencia."""
    if not predecessor.planned_start or not predecessor.planned_end:
        return None
    lagged_start = add_working_days(predecessor.planned_start, dependency.lag_days, holidays)
    lagged_end = add_working_days(predecessor.planned_end, dependency.lag_days, holidays)
    if dependency.dependency_type == "FS":
        return next_working_day(add_working_days(lagged_end, 1, holidays), holidays)
    if dependency.dependency_type == "SS":
        return next_working_day(lagged_start, holidays)
    if dependency.dependency_type == "FF":
        return task_start(lagged_end, successor.planned_duration_days, holidays)
    return task_start(lagged_start, successor.planned_duration_days, holidays)


def recalculate_project(project_id: str, session: Session) -> list[Task]:
    """Recalcula sucesoras en orden topológico dentro de la transacción actual."""
    tasks = list(session.scalars(select(Task).where(Task.project_id == project_id)))
    dependencies = list(
        session.scalars(
            select(TaskDependency)
            .join(Task, Task.id == TaskDependency.predecessor_id)
            .where(Task.project_id == project_id)
        )
    )
    ordered = topological_order(tasks, dependencies)
    holidays = working_days(project_id, session)
    incoming: dict[str, list[TaskDependency]] = defaultdict(list)
    for dependency in dependencies:
        incoming[dependency.successor_id].append(dependency)
    task_map = {task.id: task for task in tasks}
    for task in ordered:
        if not task.planned_start:
            continue
        task.planned_start = next_working_day(task.planned_start, holidays)
        task.planned_end = task_end(task.planned_start, task.planned_duration_days, holidays)
        for dependency in incoming[task.id]:
            constraint = _constraint_start(
                task_map[dependency.predecessor_id], task, dependency, holidays
            )
            if constraint and constraint > task.planned_start:
                task.planned_start = constraint
                task.planned_end = task_end(task.planned_start, task.planned_duration_days, holidays)
        task.version += 1
    return ordered
