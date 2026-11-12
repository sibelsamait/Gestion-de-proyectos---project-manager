"""Pruebas del impacto estructurado de cambios aprobados."""

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    ChangeApplication,
    ChangeRequest,
    Project,
    Resource,
    Task,
    TaskResourceAssignment,
)
from app.services.change_service import ChangeError, approve_change
from app.services.costs import project_costs


def test_structured_change_updates_schedule_cost_and_resource(app):
    with app.app_context():
        project = Project(
            code="IMPACT",
            name="Impacto",
            status="planificado",
            authorized_budget=Decimal(1000),
        )
        task = Task(
            project_id=project.id,
            name="Actividad",
            planned_start=date(2026, 11, 9),
            planned_end=date(2026, 11, 10),
            planned_duration_days=2,
        )
        resource = Resource(
            project_id=project.id,
            type="Profesional",
            name="Profesional",
            hours_per_week=Decimal(40),
            weeks=Decimal(1),
            hourly_rate=Decimal(100),
        )
        db.session.add(project)
        db.session.flush()
        task.project_id = project.id
        resource.project_id = project.id
        db.session.add_all([task, resource])
        db.session.flush()
        change = ChangeRequest(
            project_id=project.id,
            change_code="CH-IMPACT",
            requester_id="requester",
            description="Impacto estructurado",
            change_type="costo",
            priority="alta",
            risk="medio",
            impact={
                "additional_days": {"task_id": task.id, "days": 2},
                "additional_cost": "500",
                "additional_resource": {
                    "task_id": task.id,
                    "resource_id": resource.id,
                    "hours": "8",
                },
            },
            stage="Decisión",
            status="pending",
        )
        db.session.add(change)
        db.session.commit()

        applications = approve_change(db.session, change, "admin")
        db.session.commit()

        assert project.authorized_budget == Decimal("1500.00")
        assert task.planned_duration_days == 4
        assert task.planned_end == date(2026, 11, 12)
        assignment = db.session.get(
            TaskResourceAssignment,
            (task.id, resource.id),
        )
        assert assignment is not None
        assert assignment.planned_units == Decimal("0.25")
        assert project_costs(db.session, project.id)["Cambios"] == Decimal("500.00")
        assert {
            application.attribute for application in applications
        } >= {
            "planned_duration_days",
            "planned_end",
            "planned_units:" + resource.id,
            "planned_cost_adjustment",
        }


def test_structured_change_rejects_invalid_activity_without_persisting(app):
    with app.app_context():
        project = Project(code="INVALID-IMPACT", name="Inválido", status="planificado")
        db.session.add(project)
        db.session.flush()
        change = ChangeRequest(
            project_id=project.id,
            change_code="CH-INVALID",
            requester_id="requester",
            description="Fecha inválida",
            change_type="tiempo",
            priority="alta",
            risk="alto",
            impact={"additional_days": {"task_id": "missing", "days": 3}},
            stage="Decisión",
            status="pending",
        )
        db.session.add(change)
        db.session.commit()
        with pytest.raises(ChangeError, match="actividad o sus fechas"):
            approve_change(db.session, change, "admin")
        db.session.rollback()
        assert project.authorized_budget == Decimal(0)
        assert ChangeApplication.query.count() == 0
