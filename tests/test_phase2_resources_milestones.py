"""Pruebas de recursos temporales y asociaciones de hitos."""

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    KpiDefinition,
    Milestone,
    Project,
    Resource,
    Task,
    TaskResourceAssignment,
)
from app.services.costs import professional_overallocation_details


def test_overallocation_detects_weekly_and_daily_overlap(app):
    with app.app_context():
        project = Project(code="OVER", name="Sobreasignación", status="planificado")
        resource = Resource(
            project_id=project.id,
            type="Profesional",
            name="Ana",
            hourly_rate=Decimal(100),
            hours_per_week=Decimal(40),
            daily_max_hours=Decimal(8),
        )
        db.session.add(project)
        db.session.flush()
        resource.project_id = project.id
        db.session.add(resource)
        db.session.flush()
        tasks = [
            Task(
                project_id=project.id,
                name="Tarea A",
                planned_start=date(2026, 11, 9),
                planned_end=date(2026, 11, 13),
                planned_duration_days=5,
            ),
            Task(
                project_id=project.id,
                name="Tarea B",
                planned_start=date(2026, 11, 9),
                planned_end=date(2026, 11, 13),
                planned_duration_days=5,
            ),
        ]
        db.session.add_all(tasks)
        db.session.flush()
        db.session.add_all(
            [
                TaskResourceAssignment(task_id=task.id, resource_id=resource.id, planned_units=1)
                for task in tasks
            ]
        )
        details = professional_overallocation_details(db.session, project.id)
        assert details[resource.id]["weekly"] == Decimal("40.00")
        assert details[resource.id]["daily"]["2026-11-09"] == Decimal("8.00")
        assert len(details[resource.id]["daily"]) == 5


def test_milestone_can_link_tasks_and_kpis(app):
    with app.app_context():
        project = Project(code="LINK", name="Asociaciones", status="planificado")
        db.session.add(project)
        db.session.flush()
        task = Task(project_id=project.id, name="Actividad")
        milestone = Milestone(project_id=project.id, name="Entrega")
        kpi = KpiDefinition(
            project_id=project.id,
            code="HITO-01",
            name="Cumplimiento",
            scope="milestone",
            variables=["hitos_en_plazo"],
            formula="hitos_en_plazo",
            direction="higher",
            target=1,
            thresholds={"green": 1, "yellow": 0},
            periodicity="manual",
            source="manual",
        )
        db.session.add_all([task, milestone, kpi])
        db.session.flush()
        milestone.tasks.append(task)
        milestone.kpis.append(kpi)
        db.session.commit()
        db.session.expire_all()
        stored = db.session.get(Milestone, milestone.id)
        assert stored is not None
        assert [linked.id for linked in stored.tasks] == [task.id]
        assert [linked.id for linked in stored.kpis] == [kpi.id]
