"""Pruebas de endpoints Gantt y tableros."""

from datetime import UTC, date, datetime
from decimal import Decimal

from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import (
    ChangeRequest,
    ExchangeRate,
    Milestone,
    Project,
    ProjectMembership,
    Resource,
    Task,
    User,
)


def project_client(client, app):
    register(client, "dashboard@example.com")
    with app.app_context():
        user = User.query.filter_by(email="dashboard@example.com").one()
        user.role = "admin"
        project = Project(code="DASH", name="Dashboard", status="planificado")
        db.session.add(project)
        db.session.flush()
        db.session.add(ProjectMembership(project_id=project.id, user_id=user.id, membership_role="manager"))
        db.session.add(
            Task(
                project_id=project.id,
                name="Tarea visible",
                planned_start=date(2026, 1, 5),
                planned_end=date(2026, 1, 7),
                planned_duration_days=3,
                progress_percent=25,
            )
        )
        db.session.add(Milestone(project_id=project.id, name="Hito", committed_date=date(2026, 1, 7)))
        db.session.add(
            Resource(
                project_id=project.id,
                type="Profesional",
                name="Profesional",
                hours_per_week=Decimal(40),
            )
        )
        db.session.add(
            ChangeRequest(
                project_id=project.id,
                change_code="CH-DASH",
                requester_id=user.id,
                description="Cambio demostrativo",
                change_type="tiempo",
                priority="media",
                risk="bajo",
                impact={},
            )
        )
        db.session.commit()
        project_id = project.id
    login(client, "dashboard@example.com")
    return project_id


def test_gantt_and_dashboard_json_are_project_scoped(client, app):
    project_id = project_client(client, app)
    gantt = client.get(f"/api/projects/{project_id}/gantt")
    assert gantt.status_code == 200
    payload = gantt.get_json()
    assert payload["tasks"][0]["name"] == "Tarea visible"
    assert payload["milestones"][0]["name"] == "Hito"
    assert payload["dependencies"] == []

    tracking = client.get(f"/api/projects/{project_id}/tracking")
    assert tracking.status_code == 200
    assert tracking.get_json()["task_counts"]["total"] == 1

    changes = client.get(f"/api/projects/{project_id}/changes-dashboard")
    assert changes.status_code == 200
    assert changes.get_json()["total"] == 1


def test_dashboard_pages_render_accessible_tables(client, app):
    project_id = project_client(client, app)
    tracking = client.get(f"/projects/{project_id}/tracking")
    changes = client.get(f"/projects/{project_id}/changes")
    assert tracking.status_code == 200
    assert b"Alternativa textual del Gantt" in tracking.data
    assert changes.status_code == 200
    assert b"Solicitudes por estado" in changes.data


def test_dashboard_rejects_unknown_currency(client, app):
    project_id = project_client(client, app)
    response = client.get(f"/api/projects/{project_id}/tracking?currency=EUR")
    assert response.status_code == 400


def test_tracking_converts_costs_and_preserves_metadata(client, app):
    project_id = project_client(client, app)
    with app.app_context():
        db.session.add(
            ExchangeRate(
                indicator="USD",
                rate_date=date.today(),
                value=Decimal(1000),
                source="test",
                fetched_at=datetime.now(UTC),
            )
        )
        db.session.commit()
    response = client.get(f"/api/projects/{project_id}/tracking?currency=USD")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["currency"] == "USD"
    assert payload["rate_date"] == date.today().isoformat()
    assert payload["is_stale"] is False
    assert payload["professional_utilization"]["percent"] == 0
