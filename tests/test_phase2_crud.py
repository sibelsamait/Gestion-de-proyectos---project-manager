from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import Project, Resource, Task, User


def admin_client(client, app):
    register(client, "admin@example.com")
    with app.app_context():
        user = User.query.filter_by(email="admin@example.com").one()
        user.role = "admin"
        db.session.commit()
    login(client, "admin@example.com")


def test_project_and_work_item_validation(client, app):
    admin_client(client, app)
    response = client.post(
        "/projects/new",
        data={"code": "demo", "name": "Demo", "authorized_budget": "-1"},
        follow_redirects=True,
    )
    assert b"no puede ser negativo" in response.data
    response = client.post(
        "/projects/new",
        data={
            "code": "demo",
            "name": "Demo",
            "authorized_budget": "1000.50",
            "planned_start": "2026-01-10",
            "planned_end": "2026-01-01",
        },
        follow_redirects=True,
    )
    assert b"no puede preceder" in response.data
    response = client.post(
        "/projects/new",
        data={"code": "demo", "name": "Demo", "authorized_budget": "1000.50"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        project = Project.query.one()
        project_id = project.id
    response = client.post(
        f"/projects/{project_id}/task/new",
        data={"name": "Tarea", "planned_duration_days": "3", "progress_percent": "10"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert Task.query.one().planned_duration_days == 3


def test_resource_rejects_negative_values(client, app):
    admin_client(client, app)
    client.post("/projects/new", data={"code": "r1", "name": "Recursos"})
    with app.app_context():
        project_id = Project.query.one().id
    response = client.post(
        f"/projects/{project_id}/resource/new",
        data={"name": "Material", "type": "Material", "quantity": "-2"},
        follow_redirects=True,
    )
    assert b"no puede ser negativo" in response.data
    with app.app_context():
        assert Resource.query.count() == 0
