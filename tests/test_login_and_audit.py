"""Pruebas del inicio de sesión simple y de la auditoría reducida."""

from support import create_user
from test_phase6_pdf import authenticated_project

from app.extensions import db
from app.models import AuditLog, ProjectMember, User


def test_pages_require_login(anon_client):
    response = anon_client.get("/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    assert anon_client.get("/api/projects/x/tracking").status_code == 401
    assert anon_client.get("/auth/login").status_code == 200


def test_login_compares_plain_text_password(anon_client, app):
    create_user(app, "ana@example.com", "Ana")
    wrong = anon_client.post("/auth/login", data={"email": "ana@example.com", "password": "otra"})
    assert "Correo o contraseña incorrectos.".encode() in wrong.data
    ok = anon_client.post(
        "/auth/login", data={"email": " ANA@example.com ", "password": "una-clave-segura-123"}
    )
    assert ok.status_code == 302
    assert ok.headers["Location"].endswith("/dashboard")
    assert anon_client.get("/dashboard").status_code == 200
    anon_client.post("/auth/logout")
    assert anon_client.get("/dashboard").status_code == 302


def test_password_is_stored_as_given(app):
    user_id = create_user(app, "texto@example.com")
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.password == "una-clave-segura-123"
        assert user.password_matches("una-clave-segura-123")
        assert not user.password_matches("UNA-CLAVE-SEGURA-123")


def test_inactive_user_cannot_login(anon_client, app):
    user_id = create_user(app, "baja@example.com")
    with app.app_context():
        db.session.get(User, user_id).is_active = False
        db.session.commit()
    response = anon_client.post("/auth/login", data={"email": "baja@example.com", "password": "una-clave-segura-123"})
    assert "Correo o contraseña incorrectos.".encode() in response.data


def test_login_only_redirects_to_internal_paths(anon_client, app):
    create_user(app, "ruta@example.com")
    data = {"email": "ruta@example.com", "password": "una-clave-segura-123"}
    inside = anon_client.post("/auth/login?next=/projects/new", data=data)
    assert inside.headers["Location"].endswith("/projects/new")
    anon_client.post("/auth/logout")
    outside = anon_client.post("/auth/login?next=//evil.example", data=data)
    assert outside.headers["Location"].endswith("/dashboard")


def test_audit_records_email_role_change_description_and_time(client, app):
    project_id = authenticated_project(client, app)
    client.post(f"/projects/{project_id}/milestone/new", data={"name": "Entrega"})
    with app.app_context():
        event = AuditLog.query.filter_by(action="milestone.created").one()
        assert event.user_email == "tester@example.com"
        assert event.role == "admin"
        assert event.description == "PDF-1 · Hito «Entrega» creado"
        assert event.occurred_at is not None


def test_audit_uses_project_membership_role(anon_client, app):
    project_id = authenticated_project(anon_client, app)
    create_user(app, "gestor@example.com", "Gestor")
    with app.app_context():
        db.session.add(ProjectMember(project_id=project_id, email="gestor@example.com", role="gestor"))
        db.session.commit()
    anon_client.post("/auth/login", data={"email": "gestor@example.com", "password": "una-clave-segura-123"})
    anon_client.post(f"/projects/{project_id}/task/new", data={"name": "Planificar"})
    with app.app_context():
        event = AuditLog.query.filter_by(action="task.created").one()
        assert (event.user_email, event.role) == ("gestor@example.com", "gestor")


def test_failed_validation_does_not_leave_audit_event(client, app):
    project_id = authenticated_project(client, app)
    client.post(f"/projects/{project_id}/resource/new", data={"name": "X", "type": "invalido"})
    with app.app_context():
        assert AuditLog.query.count() == 0
