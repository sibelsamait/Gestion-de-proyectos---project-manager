"""Pruebas de generación del informe PDF."""

from datetime import UTC, date, datetime
from decimal import Decimal

from support import create_user

from app.extensions import db
from app.models import ExchangeRate, Project, ProjectMember, Task, User


def authenticated_project(client, app, member_email="tester@example.com", role="admin"):
    user_id = create_user(app, "privacy@example.com")
    with app.app_context():
        user = db.session.get(User, user_id)
        project = Project(
            code="PDF-1",
            name="Informe",
            status="planificado",
            authorized_budget=Decimal(1000),
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(ProjectMember(project_id=project.id, email=member_email, role=role))
        if user.email != member_email:
            db.session.add(ProjectMember(project_id=project.id, email=user.email, role="gestor"))
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


def test_only_listed_emails_reach_a_project(client, app):
    first_project = authenticated_project(client, app)
    with app.app_context():
        other = Project(code="PDF-2", name="Otro", status="planificado")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    assert client.get(f"/projects/{other_id}/export_pdf").status_code == 403
    assert client.get(f"/projects/{other_id}").status_code == 403
    assert client.get(f"/projects/{first_project}/export_pdf").status_code == 200
    assert client.get("/projects/no-existe/export_pdf").status_code == 404
