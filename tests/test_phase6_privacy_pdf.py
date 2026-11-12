"""Pruebas de privacidad, PDF y páginas legales."""

from datetime import UTC, date, datetime
from decimal import Decimal

from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import ExchangeRate, Project, ProjectMembership, Task, User
from app.services.pdf_report import _gantt_drawing


def authenticated_project(client, app):
    register(client, "privacy@example.com")
    login(client, "privacy@example.com")
    with app.app_context():
        user = User.query.filter_by(email="privacy@example.com").one()
        user.role = "admin"
        project = Project(
            code="PDF-1",
            name="Informe",
            status="planificado",
            authorized_budget=Decimal(1000),
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(ProjectMembership(project_id=project.id, user_id=user.id, membership_role="manager"))
        db.session.add(
            Task(
                project_id=project.id,
                name="Tarea PDF",
                planned_start=date(2026, 1, 5),
                planned_end=date(2026, 1, 6),
                planned_duration_days=2,
            )
        )
        db.session.commit()
        return project.id


def test_pdf_is_generated_in_memory_for_project_member(client, app):
    project_id = authenticated_project(client, app)
    response = client.get(f"/projects/{project_id}/export_pdf")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_pdf_accepts_currency_with_generation_rate(client, app):
    project_id = authenticated_project(client, app)
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
    response = client.get(f"/projects/{project_id}/export_pdf?currency=USD")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF")


def test_pdf_gantt_is_drawn_with_shapes(app):
    with app.app_context():
        task = Task(
            name="Tarea dibujada",
            planned_start=date(2026, 1, 5),
            planned_end=date(2026, 1, 7),
            planned_duration_days=3,
            progress_percent=50,
        )
        drawing = _gantt_drawing([task], [], [])
        assert drawing is not None
        assert len(drawing.contents) >= 4


def test_privacy_export_and_anonymization(client, app):
    project_id = authenticated_project(client, app)
    exported = client.get("/privacy/export")
    assert exported.status_code == 200
    assert exported.get_json()["user"]["email"] == "privacy@example.com"

    deleted = client.post("/privacy/delete")
    assert deleted.status_code == 302
    with app.app_context():
        user = User.query.filter_by(id=User.query.first().id).one()
        assert user.is_active is False
        assert user.name == "Usuario anonimizado"
        assert user.email.endswith("@invalid.local")
        assert ProjectMembership.query.count() == 0
        assert project_id is not None


def test_legal_pages_and_access_denied_for_another_project(client, app):
    assert client.get("/privacidad").status_code == 200
    assert client.get("/terminos").status_code == 200
    first_project = authenticated_project(client, app)
    with app.app_context():
        User.query.filter_by(email="privacy@example.com").one().role = "usuario_proyecto"
        other = Project(code="PDF-2", name="Otro", status="planificado")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    assert client.get(f"/projects/{other_id}/export_pdf").status_code == 403
    assert client.get(f"/projects/{first_project}/export_pdf").status_code == 200
