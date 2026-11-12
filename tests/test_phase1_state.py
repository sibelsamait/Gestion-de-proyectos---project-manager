"""Pruebas del recálculo coordinado y permisos de Fase 1."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.extensions import db
from app.models import ChangeRequest, Project, ProjectMembership, Task, User
from app.services.project_state import recalculate_project_state


def _user(user_id: str, role: str) -> User:
    user = User(
        id=user_id,
        name=user_id,
        email=f"{user_id}@example.com",
        role=role,
        terms_accepted_at=datetime.now(UTC),
    )
    user.set_password("una-clave-segura-123")
    return user


def test_recalculate_project_state_updates_progress_atomically(app):
    with app.app_context():
        project = Project(code="STATE", name="Estado", status="planificado")
        db.session.add(project)
        db.session.flush()
        db.session.add_all(
            [
                Task(
                    project_id=project.id,
                    name="Uno",
                    planned_start=date(2026, 1, 5),
                    planned_duration_days=2,
                    progress_percent=Decimal(40),
                ),
                Task(
                    project_id=project.id,
                    name="Dos",
                    planned_start=date(2026, 1, 7),
                    planned_duration_days=1,
                    progress_percent=Decimal(80),
                ),
            ]
        )
        db.session.flush()
        state = recalculate_project_state(db.session, project.id)
        assert state.progress_percent == Decimal("60.00")
        assert project.progress_percent == Decimal("60.00")
        db.session.commit()


def test_read_only_role_cannot_approve_but_director_can(client, app):
    with app.app_context():
        readonly = _user("readonly", "solo_lectura")
        director = _user("director", "usuario_proyecto")
        project = Project(
            code="ROLE",
            name="Permisos",
            status="planificado",
            director_id=director.id,
        )
        db.session.add_all([readonly, director, project])
        db.session.flush()
        db.session.add_all(
            [
                ProjectMembership(project_id=project.id, user_id=readonly.id, membership_role="member"),
                ProjectMembership(project_id=project.id, user_id=director.id, membership_role="member"),
                ChangeRequest(
                    project_id=project.id,
                    change_code="CH-ROLE",
                    requester_id=readonly.id,
                    description="Cambio",
                    change_type="costo",
                    priority="baja",
                    risk="bajo",
                    impact={"budget_delta": "1"},
                    stage="Decisión",
                    status="pending",
                ),
            ]
        )
        db.session.commit()
        change_id = ChangeRequest.query.one().id
        project_id = project.id

    client.post(
        "/auth/login",
        data={"email": "readonly@example.com", "password": "una-clave-segura-123"},
    )
    assert client.post(f"/api/projects/{project_id}/changes/{change_id}/approve").status_code == 403
    client.post("/auth/logout")
    client.post(
        "/auth/login",
        data={"email": "director@example.com", "password": "una-clave-segura-123"},
    )
    assert client.post(f"/api/projects/{project_id}/changes/{change_id}/approve").status_code == 200
