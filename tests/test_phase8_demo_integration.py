"""Prueba integrada de las tres acciones de demostración de la Fase 8."""

from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import ChangeRequest, KpiDefinition, Project, Resource, Task
from app.services.change_service import approve_change
from app.services.costs import task_cost
from app.services.dashboard import change_dashboard, gantt_data, tracking_dashboard
from app.services.project_state import recalculate_project_state
from scripts.seed_demo import seed_demo


def _snapshot(project: Project, task: Task) -> dict:
    """Obtiene los indicadores visibles que deben actualizarse."""
    tracking = tracking_dashboard(db.session, project)
    changes = change_dashboard(db.session, project.id)
    gantt = gantt_data(db.session, project.id)
    kpis = {
        kpi.code: kpi.result
        for kpi in db.session.scalars(
            select(KpiDefinition).where(KpiDefinition.project_id == project.id)
        )
    }
    task_data = next(item for item in gantt["tasks"] if item["id"] == task.id)
    return {
        "task_end": task_data["planned_end"],
        "planned_cost": tracking["earned_value"]["costo_estimado_terminar"],
        "tracking_costs": tracking["costs_by_category"],
        "tracking_kpis": tracking["kpis"],
        "change_kpis": changes["kpis"],
        "change_cost": changes["estimated_cost"],
        "change_project_state": changes["project_state"],
        "tracking_progress": tracking["progress"],
        "change_total": changes["total"],
        "kpis": kpis,
    }


def test_demo_three_actions_update_all_visible_outputs(app):
    """Ejecuta duración, recurso y cambio aprobado en el orden de la demo."""
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        task = db.session.scalar(select(Task).where(Task.project_id == project.id))
        resource = db.session.scalar(select(Resource).where(Resource.project_id == project.id))
        change = db.session.scalar(
            select(ChangeRequest).where(
                ChangeRequest.project_id == project.id,
                ChangeRequest.stage == "Decisión",
            )
        )
        assert project and task and resource and change

        before_duration = _snapshot(project, task)
        before_task_cost = task_cost(db.session, task.id).planned
        old_end = task.planned_end
        task.planned_duration_days += 1
        recalculate_project_state(db.session, project.id)
        after_duration = _snapshot(project, task)
        assert after_duration["task_end"] != before_duration["task_end"]
        assert after_duration["tracking_kpis"]
        assert after_duration["change_kpis"]
        after_task_cost = task_cost(db.session, task.id).planned
        expected_delta = (
            Decimal(40) * Decimal(4) / Decimal(5) * Decimal(35)
            - Decimal(40) * Decimal(3) / Decimal(5) * Decimal(35)
        )
        assert after_task_cost - before_task_cost == expected_delta
        assert after_duration["tracking_costs"] != before_duration["tracking_costs"]
        assert after_duration["change_project_state"]["planned_duration_days"] != (
            before_duration["change_project_state"]["planned_duration_days"]
        )
        assert all(
            item["measurement_count"] > 0
            or item["code"] in {"CHG-ADOPCION", "CHG-SATISFACCION", "CHG-RESISTENCIA"}
            for item in after_duration["tracking_kpis"] + after_duration["change_kpis"]
        )
        assert task.planned_end != old_end

        before_resource = _snapshot(project, task)
        resource.hourly_rate += Decimal(10)
        recalculate_project_state(db.session, project.id)
        after_resource = _snapshot(project, task)
        assert after_resource["tracking_costs"] != before_resource["tracking_costs"]
        assert after_resource["tracking_kpis"] != before_resource["tracking_kpis"]
        assert after_resource["change_kpis"]
        assert after_resource["task_end"] == before_resource["task_end"]
        assert after_resource["change_project_state"]["planned_cost"] != (
            before_resource["change_project_state"]["planned_cost"]
        )

        change.impact = {
            "additional_days": {"task_id": task.id, "days": 1},
            "additional_cost": "300",
            "additional_resource": {
                "task_id": task.id,
                "resource_id": resource.id,
                "hours": "8",
            },
        }
        before_approval = _snapshot(project, task)
        approve_change(db.session, change, "admin")
        db.session.commit()
        after_approval = _snapshot(project, task)
        assert after_approval["task_end"] != before_approval["task_end"]
        assert after_approval["tracking_costs"] != before_approval["tracking_costs"]
        assert after_approval["tracking_kpis"] != before_approval["tracking_kpis"]
        assert after_approval["change_kpis"] != before_approval["change_kpis"]
        assert after_approval["change_project_state"]["planned_cost"] != (
            before_approval["change_project_state"]["planned_cost"]
        )
        assert after_approval["change_total"] == before_approval["change_total"]
