"""Pruebas del motor KPI y gestión del cambio."""

from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    ChangeApplication,
    ChangeRequest,
    KpiDefinition,
    KpiMeasurement,
    Project,
    Task,
    User,
)
from app.services.change_service import ChangeError, approve_change
from app.services.kpi_engine import KpiError, evaluate_kpi


def test_kpi_is_safe_and_keeps_history(app):
    with app.app_context():
        project = Project(code="KPI", name="Indicadores", status="planificado")
        db.session.add(project)
        db.session.flush()
        kpi = KpiDefinition(
            project_id=project.id,
            code="AVANCE",
            name="Avance",
            scope="project",
            variables=["trabajo_completado", "trabajo_total"],
            formula="trabajo_completado / trabajo_total * 100",
            direction="higher",
            target=Decimal(80),
            thresholds={"green": 80, "yellow": 50},
            source="automatic",
            periodicity="manual",
        )
        db.session.add(kpi)
        db.session.flush()
        evaluate_kpi(
            db.session,
            kpi,
            {"trabajo_completado": Decimal(8), "trabajo_total": Decimal(10)},
        )
        db.session.commit()
        assert kpi.result == Decimal(80)
        assert kpi.status == "green"
        assert KpiMeasurement.query.count() == 1
        kpi.formula = "__import__('os').system('x')"
        with pytest.raises(KpiError):
            evaluate_kpi(db.session, kpi, {"trabajo_completado": 1, "trabajo_total": 1})


def test_change_approval_is_atomic_and_traceable(app):
    with app.app_context():
        project = Project(
            code="CHANGE",
            name="Cambios",
            status="planificado",
            authorized_budget=Decimal(1000),
        )
        db.session.add(project)
        db.session.flush()
        task = Task(
            project_id=project.id,
            name="Entrega",
            planned_start=date(2026, 1, 5),
            planned_end=date(2026, 1, 6),
            planned_duration_days=2,
        )
        db.session.add(task)
        db.session.flush()
        change = ChangeRequest(
            project_id=project.id,
            change_code="CH-1",
            requester_id="requester",
            description="Aumentar presupuesto",
            change_type="costo",
            priority="alta",
            risk="medio",
            impact={"budget_delta": "250", "tasks": [{"task_id": task.id, "planned_end": "2026-01-08"}]},
            stage="Decisión",
            status="pending",
        )
        db.session.add(change)
        db.session.commit()
        applications = approve_change(db.session, change, "admin")
        db.session.commit()
        assert len(applications) == 2
        assert project.authorized_budget == Decimal(1250)
        assert ChangeApplication.query.count() == 2
        assert change.status == "approved"


def test_change_rejects_unauthorized_role_and_invalid_impact(app):
    with app.app_context():
        project = Project(code="CHANGE2", name="Cambios", status="planificado")
        user = User(
            id="requester",
            name="Solicitante",
            email="requester@example.com",
            password_hash="not-used",
            terms_accepted_at=date.today(),
        )
        db.session.add_all([project, user])
        db.session.flush()
        change = ChangeRequest(
            project_id=project.id,
            change_code="CH-2",
            requester_id=user.id,
            description="Cambio",
            change_type="tiempo",
            priority="alta",
            risk="alto",
            impact={"budget_delta": "100"},
            stage="Decisión",
            status="pending",
        )
        db.session.add(change)
        db.session.commit()
        with pytest.raises(ChangeError, match="autorizado"):
            approve_change(db.session, change, "member")
        change.impact = {"budget_delta": "-999"}
        with pytest.raises(ChangeError, match="Presupuesto"):
            approve_change(db.session, change, "admin")
        db.session.rollback()
        assert project.authorized_budget == Decimal(0)
        assert ChangeApplication.query.count() == 0
