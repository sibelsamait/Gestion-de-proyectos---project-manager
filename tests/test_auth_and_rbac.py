"""Pruebas de autenticación, CSRF/RBAC y auditoría."""

from app.extensions import db
from app.models import AuditLog, Project, ProjectMembership, User


def register(client, email="user@example.com"):
    return client.post(
        "/auth/register",
        data={
            "name": "Usuario Demo",
            "email": email,
            "password": "una-clave-segura-123",
            "password_confirmation": "una-clave-segura-123",
            "accept_terms": "y",
        },
        follow_redirects=True,
    )


def login(client, email="user@example.com"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": "una-clave-segura-123"},
        follow_redirects=True,
    )


def test_register_login_and_audit(client, app):
    response = register(client)
    assert response.status_code == 200
    assert b"Ya puedes iniciar sesi" in response.data
    response = login(client)
    assert response.status_code == 200
    with app.app_context():
        user = User.query.one()
        assert user.check_password("una-clave-segura-123")
        assert user.terms_accepted_at is not None
        assert AuditLog.query.filter_by(action="user.registered").count() == 1
        assert AuditLog.query.filter_by(action="user.login").count() == 1


def test_project_requires_membership(client, app):
    register(client)
    login(client)
    with app.app_context():
        project = Project(code="PRJ-1", name="Privado", status="planificado")
        db.session.add(project)
        db.session.commit()
        project_id = project.id
    assert client.get(f"/projects/{project_id}").status_code == 403

    with app.app_context():
        user = User.query.one()
        db.session.add(ProjectMembership(project_id=project_id, user_id=user.id))
        db.session.commit()
    assert client.get(f"/projects/{project_id}").status_code == 200
