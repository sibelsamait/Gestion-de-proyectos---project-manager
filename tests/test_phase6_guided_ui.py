"""Pruebas de la ruta guiada y navegación accesible."""

from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import Project, ProjectMembership, User


def test_project_detail_has_guided_route_and_ordered_sidebar(client, app):
    register(client, "guided@example.com")
    login(client, "guided@example.com")
    with app.app_context():
        user = User.query.filter_by(email="guided@example.com").one()
        user.role = "admin"
        project = Project(code="GUIDED", name="Ruta", status="planificado")
        db.session.add(project)
        db.session.flush()
        db.session.add(
            ProjectMembership(
                project_id=project.id,
                user_id=user.id,
                membership_role="manager",
            )
        )
        db.session.commit()
        project_id = project.id
    response = client.get(f"/projects/{project_id}")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Ruta del proyecto" in body
    assert "Completa el paso anterior" in body
    sidebar = body.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    assert sidebar.index("Datos del proyecto") < sidebar.index("Actividades")
    assert sidebar.index("Actividades") < sidebar.index("Recursos y costos")
    assert 'aria-label="Navegación del proyecto"' in body
