"""Pruebas de CRUD visual y KPI de gestión del cambio."""

from sqlalchemy import select
from test_auth_and_rbac import login, register

from app.extensions import db
from app.models import (
    ChangeRequest,
    KpiAlert,
    KpiDefinition,
    KpiMeasurement,
    Project,
    ProjectMembership,
    Task,
    User,
)
from app.services.project_state import recalculate_project_state
from scripts.seed_demo import seed_demo


def test_change_kpis_have_values_history_alerts_and_visible_crud(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        recalculate_project_state(db.session, project.id)
        db.session.commit()
        codes = {
            kpi.code
            for kpi in db.session.scalars(
                select(KpiDefinition).where(
                    KpiDefinition.project_id == project.id,
                    KpiDefinition.scope == "change",
                )
            )
        }
        assert len(codes) == 12
        assert db.session.scalar(
            select(KpiMeasurement.id)
            .join(KpiDefinition, KpiDefinition.id == KpiMeasurement.kpi_id)
            .where(KpiDefinition.project_id == project.id, KpiDefinition.scope == "change")
        )
        assert db.session.scalar(
            select(KpiAlert.id)
            .join(KpiDefinition, KpiDefinition.id == KpiAlert.kpi_id)
            .where(KpiDefinition.project_id == project.id, KpiDefinition.scope == "change")
        )
        project_id = project.id

    register(client, "kpi-crud@example.com")
    login(client, "kpi-crud@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "kpi-crud@example.com"))
        project = db.session.get(Project, project_id)
        project.director_id = user.id
        db.session.add(
            ProjectMembership(
                project_id=project.id,
                user_id=user.id,
                membership_role="manager",
            )
        )
        db.session.commit()

    response = client.get(f"/api/projects/{project_id}/kpis")
    assert response.status_code == 200
    assert b"Crear indicador" in response.data
    assert b"Historial de mediciones" in response.data
    assert b"Alertas" in response.data
    response = client.post(
        f"/api/projects/{project_id}/kpis",
        data={
            "code": "CUSTOM-01",
            "name": "Indicador propio",
            "objective": "Mide una prueba.",
            "scope": "change",
            "variables": "cambios_totales",
            "formula": "cambios_totales",
            "unit": "solicitudes",
            "target": "5",
            "direction": "lower",
            "threshold_green": "5",
            "threshold_yellow": "10",
            "periodicity": "mensual",
            "source": "manual",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Indicador propio" in response.data
    with app.app_context():
        custom = db.session.scalar(
            select(KpiDefinition).where(KpiDefinition.code == "CUSTOM-01")
        )
        custom_id = custom.id
    response = client.post(
        f"/api/projects/{project_id}/kpis/{custom_id}/edit",
        data={
            "code": "CUSTOM-01",
            "name": "Indicador editado",
            "objective": "Mide otra cosa.",
            "scope": "change",
            "variables": "cambios_totales",
            "formula": "cambios_totales",
            "unit": "solicitudes",
            "target": "4",
            "direction": "lower",
            "threshold_green": "4",
            "threshold_yellow": "8",
            "periodicity": "semanal",
            "source": "manual",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Indicador editado" in response.data
    response = client.get(f"/api/projects/{project_id}/kpis")
    assert b"data-confirm" in response.data
    response = client.post(
        f"/api/projects/{project_id}/kpis/{custom_id}/delete",
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(KpiDefinition, custom_id) is None


def test_read_only_cannot_create_edit_or_delete_kpi(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        existing = db.session.scalar(
            select(KpiDefinition).where(KpiDefinition.project_id == project.id)
        )
        existing_id = existing.id
        project_id = project.id
    register(client, "readonly-kpi@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "readonly-kpi@example.com"))
        user.role = "solo_lectura"
        db.session.add(
            ProjectMembership(project_id=project_id, user_id=user.id, membership_role="member")
        )
        db.session.commit()
    login(client, "readonly-kpi@example.com")
    payload = {
        "code": "READONLY-01",
        "name": "No debe guardarse",
        "scope": "change",
        "variables": "cambios_totales",
        "formula": "cambios_totales",
        "target": "1",
        "direction": "higher",
        "threshold_green": "1",
        "threshold_yellow": "0",
        "periodicity": "manual",
        "source": "manual",
    }
    assert client.post(f"/api/projects/{project_id}/kpis", data=payload).status_code == 403
    assert client.post(
        f"/api/projects/{project_id}/kpis/{existing_id}/edit", data=payload
    ).status_code == 403
    assert client.post(
        f"/api/projects/{project_id}/kpis/{existing_id}/delete"
    ).status_code == 403


def test_kpi_delete_associated_to_milestone_is_blocked_with_message(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        kpi = db.session.scalar(
            select(KpiDefinition).where(KpiDefinition.project_id == project.id)
        )
        assert kpi.milestones
        project_id, kpi_id = project.id, kpi.id
    register(client, "milestone-kpi@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "milestone-kpi@example.com"))
        user.role = "admin"
        db.session.commit()
    login(client, "milestone-kpi@example.com")
    response = client.post(
        f"/api/projects/{project_id}/kpis/{kpi_id}/delete",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"No se puede eliminar este KPI porque est" in response.data
    with app.app_context():
        assert db.session.get(KpiDefinition, kpi_id) is not None


def test_kpi_rejects_unknown_variable_and_code_formula_without_saving(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        project_id = project.id
    register(client, "invalid-kpi@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "invalid-kpi@example.com"))
        user.role = "admin"
        db.session.commit()
    login(client, "invalid-kpi@example.com")
    base = {
        "name": "Inválido",
        "scope": "change",
        "target": "1",
        "direction": "higher",
        "threshold_green": "1",
        "threshold_yellow": "0",
        "periodicity": "manual",
        "source": "manual",
    }
    for code, variables, formula in (
        ("BAD-VAR", "no_permitida", "no_permitida"),
        ("BAD-CODE", "cambios_totales", "__import__('os').system('x')"),
    ):
        response = client.post(
            f"/api/projects/{project_id}/kpis",
            data={
                **base,
                "code": code,
                "variables": variables,
                "formula": formula,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(
            select(KpiDefinition).where(KpiDefinition.code.in_(("BAD-VAR", "BAD-CODE")))
        ) is None


def test_aggregate_change_metrics_use_one_to_five_scale(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        kpi = db.session.scalar(
            select(KpiDefinition).where(
                KpiDefinition.project_id == project.id,
                KpiDefinition.code == "CHG-SATISFACCION",
            )
        )
        project_id, kpi_id = project.id, kpi.id
    register(client, "metrics@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "metrics@example.com"))
        user.role = "admin"
        db.session.commit()
    login(client, "metrics@example.com")
    response = client.post(
        f"/api/projects/{project_id}/kpis/{kpi_id}/manual-measure",
        data={"manual_value": "5"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    response = client.post(
        f"/api/projects/{project_id}/kpis/{kpi_id}/manual-measure",
        data={"manual_value": "6"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"debe estar entre 1 y 5" in response.data


def test_change_request_has_visual_create_and_edit_form(client, app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        task = db.session.scalar(select(Task).where(Task.project_id == project.id))
        project_id, task_id = project.id, task.id
    register(client, "change-form@example.com")
    login(client, "change-form@example.com")
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "change-form@example.com"))
        db.session.add(ProjectMembership(project_id=project_id, user_id=user.id, membership_role="member"))
        db.session.commit()
    response = client.get(f"/api/projects/{project_id}/changes/new")
    assert response.status_code == 200
    assert b"Impacto que se aplicar" in response.data
    response = client.post(
        f"/api/projects/{project_id}/changes/new",
        data={
            "change_code": "FORM-001",
            "description": "Ajustar entrega",
            "justification": "Necesidad del cliente",
            "change_type": "tiempo",
            "priority": "alta",
            "risk": "medio",
            "committed_date": "2026-12-01",
            "estimated_cost": "100",
            "impact_task_id": task_id,
            "additional_days": "2",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        change = db.session.scalar(
            select(ChangeRequest).where(ChangeRequest.change_code == "FORM-001")
        )
        change_id = change.id
        assert change.impact["additional_days"]["days"] == 2
        user = db.session.scalar(select(User).where(User.email == "change-form@example.com"))
        user.role = "admin"
        db.session.commit()
    client.post("/auth/logout")
    login(client, "change-form@example.com")
    response = client.get(f"/api/projects/{project_id}/changes/{change_id}/edit")
    assert response.status_code == 200
    response = client.post(
        f"/api/projects/{project_id}/changes/{change_id}/edit",
        data={
            "change_code": "FORM-001",
            "description": "Ajustar entrega y pruebas",
            "change_type": "tiempo",
            "priority": "critica",
            "risk": "alto",
            "estimated_cost": "125",
            "impact_task_id": task_id,
            "additional_days": "3",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        change = db.session.get(ChangeRequest, change_id)
        assert change.description == "Ajustar entrega y pruebas"
        assert change.impact["additional_days"]["days"] == 3
