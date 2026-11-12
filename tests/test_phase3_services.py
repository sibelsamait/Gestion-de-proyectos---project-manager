"""Pruebas unitarias del scheduler y costos."""

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    NonWorkingDay,
    Project,
    Resource,
    Task,
    TaskDependency,
    TaskResourceAssignment,
)
from app.services.costs import professional_overallocations, project_costs, task_cost
from app.services.scheduler import (
    ScheduleError,
    recalculate_project,
    validate_dependency,
)


def project_with_tasks(app, dependency_type: str, lag: int = 0):
    with app.app_context():
        project = Project(code=f"P-{dependency_type}-{lag}", name="Plan", status="planificado")
        db.session.add(project)
        db.session.flush()
        predecessor = Task(
            project_id=project.id,
            name="Predecesora",
            planned_start=date(2026, 1, 5),
            planned_duration_days=2,
        )
        successor = Task(
            project_id=project.id,
            name="Sucesora",
            planned_start=date(2026, 1, 5),
            planned_duration_days=2,
        )
        db.session.add_all([predecessor, successor])
        db.session.flush()
        db.session.add(
            TaskDependency(
                predecessor_id=predecessor.id,
                successor_id=successor.id,
                dependency_type=dependency_type,
                lag_days=lag,
            )
        )
        db.session.flush()
        recalculate_project(project.id, db.session)
        result = successor.planned_start, successor.planned_end
        db.session.rollback()
        return result


@pytest.mark.parametrize(
    ("dependency_type", "expected_start"),
    [
        ("FS", date(2026, 1, 7)),
        ("SS", date(2026, 1, 5)),
        ("FF", date(2026, 1, 5)),
        ("SF", date(2026, 1, 5)),
    ],
)
def test_dependency_types(app, dependency_type, expected_start):
    start, _ = project_with_tasks(app, dependency_type)
    assert start == expected_start


def test_negative_lag_and_holiday(app):
    with app.app_context():
        project = Project(code="HOLIDAY", name="Feriados", status="planificado")
        db.session.add(project)
        db.session.flush()
        db.session.add(NonWorkingDay(project_id=project.id, day=date(2026, 1, 6), reason="Feriado"))
        first = Task(
            project_id=project.id,
            name="A",
            planned_start=date(2026, 1, 5),
            planned_duration_days=2,
        )
        second = Task(
            project_id=project.id,
            name="B",
            planned_start=date(2026, 1, 5),
            planned_duration_days=1,
        )
        db.session.add_all([first, second])
        db.session.flush()
        dependency = TaskDependency(
            predecessor_id=first.id,
            successor_id=second.id,
            dependency_type="FS",
            lag_days=-1,
        )
        db.session.add(dependency)
        recalculate_project(project.id, db.session)
        assert first.planned_end == date(2026, 1, 7)
        assert second.planned_start == date(2026, 1, 7)


def test_cycle_is_rejected_without_persisting(app):
    with app.app_context():
        project = Project(code="CYCLE", name="Ciclo", status="planificado")
        db.session.add(project)
        db.session.flush()
        first = Task(project_id=project.id, name="A")
        second = Task(project_id=project.id, name="B")
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add(
            TaskDependency(predecessor_id=first.id, successor_id=second.id, dependency_type="FS")
        )
        db.session.flush()
        cycle = TaskDependency(
            predecessor_id=second.id, successor_id=first.id, dependency_type="FS"
        )
        with pytest.raises(ScheduleError, match="ciclo"):
            validate_dependency(db.session, cycle)
        assert db.session.query(TaskDependency).count() == 1


def test_costs_use_decimal_and_detect_overallocation(app):
    with app.app_context():
        project = Project(code="COST", name="Costos", status="planificado")
        db.session.add(project)
        db.session.flush()
        professional = Resource(
            project_id=project.id,
            type="Profesional",
            name="Dev",
            hourly_rate=Decimal(50),
            hours_per_week=Decimal(40),
            weeks=Decimal(2),
        )
        material = Resource(
            project_id=project.id,
            type="Material",
            name="Material",
            quantity=Decimal(3),
            unit_cost=Decimal(10),
        )
        task = Task(
            project_id=project.id,
            name="Implementación",
            planned_start=date(2026, 1, 5),
            planned_end=date(2026, 1, 16),
            planned_duration_days=10,
        )
        db.session.add_all([professional, material, task])
        db.session.flush()
        db.session.add_all(
            [
                TaskResourceAssignment(
                    task_id=task.id,
                    resource_id=professional.id,
                    planned_units=Decimal(2),
                    actual_units=Decimal(1),
                ),
                TaskResourceAssignment(
                    task_id=task.id,
                    resource_id=material.id,
                    planned_units=Decimal(1),
                    actual_units=Decimal(1),
                ),
            ]
        )
        db.session.flush()
        breakdown = task_cost(db.session, task.id)
        assert breakdown.planned == Decimal("8030.00")
        assert breakdown.actual == Decimal("4030.00")
        assert project_costs(db.session, project.id)["Profesional"] == Decimal("8000.00")
        assert professional_overallocations(db.session, project.id) == {professional.id: Decimal("40.00")}


def test_professional_cost_uses_three_working_days_as_six_tenths_week(app):
    with app.app_context():
        project = Project(code="THREE-DAYS", name="Tres días", status="planificado")
        professional = Resource(
            project_id=project.id,
            type="Profesional",
            name="Dev",
            hourly_rate=Decimal(50),
            hours_per_week=Decimal(40),
            weeks=Decimal(99),
        )
        task = Task(
            project_id=project.id,
            name="Actividad corta",
            planned_start=date(2026, 1, 5),
            planned_end=date(2026, 1, 7),
            planned_duration_days=3,
        )
        db.session.add(project)
        db.session.flush()
        professional.project_id = project.id
        db.session.add(professional)
        task.project_id = project.id
        db.session.add(task)
        db.session.flush()
        db.session.add(
            TaskResourceAssignment(
                task_id=task.id,
                resource_id=professional.id,
                planned_units=Decimal(1),
                actual_units=Decimal(1),
            )
        )
        db.session.flush()

        assert task_cost(db.session, task.id).planned == Decimal("1200.00")
        task.actual_start = date(2026, 1, 5)
        task.actual_end = date(2026, 1, 9)
        task.actual_duration_days = 5
        assert task_cost(db.session, task.id).actual == Decimal("2000.00")
        task.actual_duration_days = 0
        assert task_cost(db.session, task.id).actual == Decimal("1200.00")
