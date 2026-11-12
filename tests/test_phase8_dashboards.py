"""Pruebas de filtros y métricas visibles de ambos tableros."""

from datetime import date

from sqlalchemy import select

from app.extensions import db
from app.models import Project
from app.services.dashboard import change_dashboard, tracking_dashboard
from scripts.seed_demo import seed_demo


def test_tracking_filters_change_tasks_costs_and_schedule(app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        all_data = tracking_dashboard(db.session, project)
        filtered = tracking_dashboard(
            db.session,
            project,
            stage="Inicio",
            date_from=date(2026, 1, 5),
            date_to=date(2026, 1, 20),
        )
        assert all_data["task_counts"]["total"] == 32
        assert filtered["task_counts"]["total"] < all_data["task_counts"]["total"]
        assert filtered["filters"]["stage"] == "Inicio"
        assert filtered["filters"]["date_from"] == "2026-01-05"
        assert filtered["tasks"]
        assert filtered["costs_by_category"] != all_data["costs_by_category"]


def test_change_dashboard_exposes_metrics_and_alert_tables(app):
    with app.app_context():
        seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        dashboard = change_dashboard(db.session, project.id, "CLP")
        assert dashboard["currency"] == "CLP"
        assert "average_days" in dashboard["implementation"]
        assert "corrective_actions" in dashboard
        assert "percent" in dashboard["effectiveness"]
        assert dashboard["adoption"]["scale"] == "1-5"
        assert set(dashboard["alerts"]) == {"overdue", "critical_risks", "unmet_kpis"}
        assert "Cierre con resultado" in dashboard["stage_completion"]
        assert "Seguimiento de adopción" in dashboard["stage_completion"]
