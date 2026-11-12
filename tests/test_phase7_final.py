"""Pruebas de integración del caso demo y coherencia de moneda."""

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    Resource,
    Task,
    TaskDependency,
)
from scripts.seed_demo import seed_demo


def test_seed_demo_has_required_case_counts(app):
    with app.app_context():
        admin_password, member_password = seed_demo()
        project = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
        assert project is not None
        assert len(admin_password) >= 18
        assert len(member_password) >= 18
        assert db.session.scalar(
            select(db.func.count(Task.id)).where(Task.project_id == project.id)
        ) == 32
        assert db.session.scalar(
            select(db.func.count(TaskDependency.predecessor_id))
            .join(Task, Task.id == TaskDependency.predecessor_id)
            .where(Task.project_id == project.id)
        ) == 4
        assert db.session.scalar(
            select(db.func.count(Milestone.id)).where(Milestone.project_id == project.id)
        ) == 6
        assert db.session.scalar(
            select(db.func.count(Resource.id)).where(Resource.project_id == project.id)
        ) == 9
        assert db.session.scalar(
            select(db.func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project.id)
        ) == 5
        assert db.session.scalar(
            select(db.func.count(KpiDefinition.id)).where(KpiDefinition.project_id == project.id)
        ) == 20
        assert {task.etapa for task in Task.query.filter_by(project_id=project.id)} == {
            "Inicio",
            "Planificación",
            "Ejecución",
            "Cierre",
        }
        assert all(milestone.tasks for milestone in Milestone.query.filter_by(project_id=project.id))
