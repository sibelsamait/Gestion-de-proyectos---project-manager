"""Pruebas del flujo secuencial y filtros de gestión del cambio."""

from datetime import UTC, datetime

import pytest

from app.extensions import db
from app.models import ChangeRequest, ChangeStageHistory, Project, User
from app.services.change_service import STAGES, ChangeError, transition_change
from app.services.dashboard import change_dashboard


def test_change_stage_requires_one_step_and_keeps_history(app):
    with app.app_context():
        user = User(
            id="actor",
            name="Actor",
            email="actor@example.com",
            password_hash="hash",
            terms_accepted_at=datetime.now(UTC),
        )
        project = Project(code="FLOW", name="Flujo", status="planificado")
        db.session.add_all([user, project])
        db.session.flush()
        change = ChangeRequest(
            project_id=project.id,
            change_code="CH-FLOW",
            requester_id=user.id,
            description="Cambio",
            change_type="tiempo",
            priority="alta",
            risk="medio",
        )
        db.session.add(change)
        db.session.flush()
        first = transition_change(db.session, change, user.id, "Clasifiqué la solicitud.")
        second = transition_change(db.session, change, user.id, "Evalué el impacto.")
        db.session.commit()
        assert first.to_stage == "Clasificación"
        assert second.to_stage == "Evaluación de impacto"
        assert change.stage == "Evaluación de impacto"
        assert ChangeStageHistory.query.count() == 2
        change.stage = STAGES[-1]
        with pytest.raises(ChangeError, match="última etapa"):
            transition_change(db.session, change, user.id, "No corresponde avanzar.")


def test_change_dashboard_applies_all_filters(app):
    with app.app_context():
        user = User(
            id="filter-user",
            name="Filtro",
            email="filter@example.com",
            password_hash="hash",
            terms_accepted_at=datetime.now(UTC),
        )
        project = Project(code="FILTER", name="Filtros", status="planificado")
        db.session.add_all([user, project])
        db.session.flush()
        db.session.add_all(
            [
                ChangeRequest(
                    project_id=project.id,
                    change_code="CH-1",
                    requester_id=user.id,
                    description="Uno",
                    change_type="costo",
                    priority="alta",
                    risk="alto",
                    responsible_id=user.id,
                ),
                ChangeRequest(
                    project_id=project.id,
                    change_code="CH-2",
                    requester_id=user.id,
                    description="Dos",
                    change_type="tiempo",
                    priority="baja",
                    risk="bajo",
                ),
            ]
        )
        db.session.commit()
        result = change_dashboard(
            db.session,
            project.id,
            status="pending",
            priority="alta",
            change_type="costo",
            responsible_id=user.id,
        )
        assert result["total"] == 1
        assert result["filters"]["priority"] == "alta"
