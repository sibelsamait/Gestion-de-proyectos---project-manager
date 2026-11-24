"""Pruebas del registro y de los roles por proyecto (admin, gestor, miembro)."""

from app.models import AuditLog, Project, ProjectMember, User

PASSWORD = "clave-demo"


def register(client, email, name="Persona", company="Empresa SpA", password=PASSWORD, confirmation=None):
    return client.post(
        "/auth/register",
        data={
            "email": email,
            "name": name,
            "company": company,
            "password": password,
            "password_confirmation": password if confirmation is None else confirmation,
        },
    )


def login(client, email, password=PASSWORD):
    return client.post("/auth/login", data={"email": email, "password": password})


def create_project(client, code="ROL-1"):
    client.post("/projects/new", data={"code": code, "name": f"Proyecto {code}"})
    return Project.query.filter_by(code=code).one().id


def test_register_creates_account_and_logs_in(anon_client, app):
    response = register(anon_client, " Nueva@Empresa.cl ", name="Nueva", company="Acme")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert anon_client.get("/dashboard").status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="nueva@empresa.cl").one()
        assert (user.name, user.company, user.password) == ("Nueva", "Acme", PASSWORD)


def test_register_validates_fields(anon_client, app):
    assert b"Las contrase" in register(anon_client, "a@b.cl", confirmation="otra").data
    assert b"La empresa es un dato obligatorio." in register(anon_client, "a@b.cl", company="").data
    assert "no es un correo válido".encode() in register(anon_client, "sin-arroba").data
    register(anon_client, "dup@b.cl")
    anon_client.post("/auth/logout")
    assert "ya está registrado".encode() in register(anon_client, "DUP@b.cl").data
    with app.app_context():
        assert User.query.count() == 1


def test_creator_becomes_admin_and_is_audited(anon_client, app):
    register(anon_client, "creador@b.cl")
    form = anon_client.get("/projects/new")
    assert form.status_code == 200
    assert b"Director del proyecto" in form.data
    with app.app_context():
        project_id = create_project(anon_client)
        member = ProjectMember.query.filter_by(project_id=project_id).one()
        assert (member.email, member.role) == ("creador@b.cl", "admin")
        event = AuditLog.query.filter_by(action="project.created").one()
        assert (event.user_email, event.role) == ("creador@b.cl", "admin")


def test_invited_email_sees_project_after_registering(app):
    admin, guest = app.test_client(), app.test_client()
    register(admin, "admin@b.cl")
    with app.app_context():
        project_id = create_project(admin)
    admin.post(f"/projects/{project_id}/members", data={"email": "Invitado@B.cl", "role": "gestor"})
    register(guest, "invitado@b.cl", name="Invitado")
    page = guest.get("/dashboard")
    assert b"ROL-1" in page.data
    assert b"Jefe de proyecto" in page.data
    assert guest.get(f"/projects/{project_id}").status_code == 200


def test_uninvited_user_cannot_see_project(app):
    admin, other = app.test_client(), app.test_client()
    register(admin, "admin@b.cl")
    with app.app_context():
        project_id = create_project(admin)
    register(other, "ajeno@b.cl")
    assert b"ROL-1" not in other.get("/dashboard").data
    assert other.get(f"/projects/{project_id}").status_code == 403
    assert other.get(f"/api/projects/{project_id}/tracking").status_code == 403


def _project_with(app, role):
    admin, user = app.test_client(), app.test_client()
    register(admin, "admin@b.cl")
    with app.app_context():
        project_id = create_project(admin)
    admin.post(f"/projects/{project_id}/members", data={"email": "user@b.cl", "role": role})
    register(user, "user@b.cl")
    return admin, user, project_id


def test_member_is_read_only(app):
    _, user, project_id = _project_with(app, "miembro")
    assert user.get(f"/projects/{project_id}?vista=tareas").status_code == 200
    assert user.get(f"/projects/{project_id}/informe").status_code == 200
    assert user.get(f"/projects/{project_id}/export_pdf").status_code == 200
    assert user.get(f"/projects/{project_id}/task/new").status_code == 403
    assert user.post(f"/projects/{project_id}/task/new", data={"name": "X"}).status_code == 403
    assert user.get(f"/projects/{project_id}/edit").status_code == 403
    assert user.post(f"/projects/{project_id}/members", data={"email": "x@b.cl", "role": "admin"}).status_code == 403
    assert user.post(f"/api/projects/{project_id}/kpis/x/measure", json={}).status_code == 403
    page = user.get(f"/projects/{project_id}?vista=tareas").data
    assert b"Nueva tarea" not in page
    assert b"Editar proyecto" not in page


def test_manager_edits_work_but_not_project_or_users(app):
    _, user, project_id = _project_with(app, "gestor")
    assert user.post(f"/projects/{project_id}/task/new", data={"name": "Planificar"}).status_code == 302
    assert user.get(f"/projects/{project_id}/edit").status_code == 403
    assert user.post(f"/projects/{project_id}/members", data={"email": "x@b.cl", "role": "miembro"}).status_code == 403
    page = user.get(f"/projects/{project_id}?vista=tareas").data
    assert b"Nueva tarea" in page
    assert b"Editar proyecto" not in page


def test_admin_manages_roles_and_keeps_one_admin(app):
    admin, user, project_id = _project_with(app, "miembro")
    with app.app_context():
        guest = ProjectMember.query.filter_by(email="user@b.cl").one()
        owner = ProjectMember.query.filter_by(email="admin@b.cl").one()
        guest_id, owner_id = guest.id, owner.id
    admin.post(f"/projects/{project_id}/members/{guest_id}/role", data={"role": "gestor"})
    assert user.post(f"/projects/{project_id}/task/new", data={"name": "Ahora sí"}).status_code == 302
    demote = admin.post(f"/projects/{project_id}/members/{owner_id}/role", data={"role": "miembro"},
                        follow_redirects=True)
    assert b"al menos un administrador" in demote.data
    removed = admin.post(f"/projects/{project_id}/members/{owner_id}/delete", follow_redirects=True)
    assert b"al menos un administrador" in removed.data
    duplicate = admin.post(f"/projects/{project_id}/members", data={"email": "USER@b.cl", "role": "admin"},
                           follow_redirects=True)
    assert "ya está en la lista".encode() in duplicate.data
    bad_role = admin.post(f"/projects/{project_id}/members", data={"email": "z@b.cl", "role": "Admin"},
                          follow_redirects=True)
    assert b"El rol debe ser uno de" in bad_role.data
    admin.post(f"/projects/{project_id}/members/{guest_id}/delete")
    assert user.get(f"/projects/{project_id}").status_code == 403
    with app.app_context():
        actions = {event.action for event in AuditLog.query.all()}
        assert {"member.added", "member.role_changed", "member.removed"} <= actions



def test_member_is_default_role_when_adding_users(app):
    admin, _, project_id = _project_with(app, "miembro")
    page = admin.get(f"/projects/{project_id}?vista=usuarios").data.decode()
    assert '<option value="miembro" selected>Miembro</option>' in page
