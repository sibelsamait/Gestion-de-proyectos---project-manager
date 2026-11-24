"""Pruebas de las vistas de portafolio, detalle por pestañas, informe y validación."""

from datetime import date

from support import create_user
from test_phase6_pdf import authenticated_project

from app.extensions import db
from app.models import Milestone, Project, ProjectMember, Resource
from app.validation import column_choices


def test_dashboard_lists_project_with_progress_and_filter(client, app):
    project_id = authenticated_project(client, app)
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert b"PDF-1" in page.data
    assert f"/projects/{project_id}/informe".encode() in page.data
    filtered = client.get("/dashboard?estado=terminado")
    assert b"Sin proyectos en este estado" in filtered.data


def test_root_redirects_to_dashboard_without_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_detail_tabs_render_and_unknown_tab_falls_back(client, app):
    project_id = authenticated_project(client, app)
    for tab in ("resumen", "tareas", "hitos", "recursos", "kpi", "cambios", "inexistente"):
        response = client.get(f"/projects/{project_id}?vista={tab}")
        assert response.status_code == 200, tab
    assert b"Tarea PDF" in client.get(f"/projects/{project_id}?vista=tareas").data
    summary = client.get(f"/projects/{project_id}").data
    assert "Preparación del informe".encode() in summary
    assert b"Estado de las tareas" in summary


def test_report_preview_flags_missing_scope_data(client, app):
    project_id = authenticated_project(client, app)
    response = client.get(f"/projects/{project_id}/informe")
    assert response.status_code == 200
    assert "Falta la descripción del proyecto.".encode() in response.data
    assert b"Exportar informe PDF" in response.data
    assert b"informe-PDF-1.pdf" in response.data


def test_pdf_without_rate_redirects_to_preview(client, app):
    project_id = authenticated_project(client, app)
    response = client.get(f"/projects/{project_id}/export_pdf?currency=UF")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/projects/{project_id}/informe")


def test_choices_come_from_database_schema():
    assert column_choices(Project.status) == ("planificado", "en_ejecucion", "suspendido", "terminado")
    assert "Profesional" in column_choices(Resource.type)


def test_milestone_form_saves_status_and_responsible(client, app):
    project_id = authenticated_project(client, app)
    user_id = create_user(app, "responsable@example.com", "Responsable")
    with app.app_context():
        db.session.add(ProjectMember(project_id=project_id, email="responsable@example.com", role="miembro"))
        db.session.commit()
    response = client.post(
        f"/projects/{project_id}/milestone/new",
        data={
            "name": "Entrega",
            "committed_date": "2026-03-01",
            "actual_date": "2026-03-02",
            "status": "cumplido",
            "responsible_id": user_id,
        },
    )
    assert response.status_code == 302
    with app.app_context():
        milestone = Milestone.query.filter_by(project_id=project_id).one()
        assert milestone.status == "cumplido"
        assert milestone.actual_date == date(2026, 3, 2)
        assert milestone.responsible_id == user_id


def test_values_must_match_database_text_exactly(client, app):
    project_id = authenticated_project(client, app)
    for status in ("Cumplido", "CUMPLIDO", "done"):
        response = client.post(
            f"/projects/{project_id}/milestone/new",
            data={"name": "Hito", "status": status},
            follow_redirects=True,
        )
        assert b"El estado del hito debe ser uno de" in response.data
    with app.app_context():
        assert Milestone.query.count() == 0
    response = client.post(
        f"/projects/{project_id}/resource/new",
        data={"name": "Licencia", "type": "licencia"},
        follow_redirects=True,
    )
    assert b"El tipo de recurso debe ser uno de" in response.data
    with app.app_context():
        assert Resource.query.count() == 0


def test_rejects_unknown_responsible_and_overlong_text(client, app):
    project_id = authenticated_project(client, app)
    response = client.post(
        f"/projects/{project_id}/task/new",
        data={"name": "Ajena", "responsible_id": "no-existe"},
        follow_redirects=True,
    )
    assert b"El responsable debe ser un usuario registrado del proyecto." in response.data
    response = client.post(
        f"/projects/{project_id}/task/new",
        data={"name": "x" * 161},
        follow_redirects=True,
    )
    assert "supera el máximo de 160 caracteres".encode() in response.data


def test_progress_cannot_exceed_100(client, app):
    project_id = authenticated_project(client, app)
    response = client.post(
        f"/projects/{project_id}/task/new",
        data={"name": "Excedida", "progress_percent": "120"},
        follow_redirects=True,
    )
    assert b"El avance no puede superar 100." in response.data
