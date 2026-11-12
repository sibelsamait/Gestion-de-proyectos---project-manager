"""Datos demo reproducibles en estructura, con credenciales aleatorias."""

import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import click
from sqlalchemy import select

from app.extensions import db
from app.models import (
    ChangeRequest,
    KpiDefinition,
    Milestone,
    Project,
    ProjectMembership,
    Resource,
    Task,
    TaskDependency,
    TaskResourceAssignment,
    User,
)


def _password() -> str:
    """Genera una contraseña demo no fija."""
    return secrets.token_urlsafe(18)


def seed_demo() -> tuple[str, str]:
    """Crea el proyecto demo y devuelve las credenciales generadas."""
    existing = db.session.scalar(select(Project).where(Project.code == "DEMO-2026"))
    if existing:
        raise RuntimeError("El proyecto demo ya existe; no se modificó ningún dato.")
    admin_password = _password()
    user_password = _password()
    admin = User(
        name="Administración Demo",
        email="admin.demo@example.invalid",
        role="admin",
        terms_accepted_at=datetime.now(UTC),
    )
    admin.set_password(admin_password)
    member = User(
        name="Usuario Proyecto Demo",
        email="usuario.demo@example.invalid",
        role="usuario_proyecto",
        terms_accepted_at=datetime.now(UTC),
    )
    member.set_password(user_password)
    db.session.add_all([admin, member])
    db.session.flush()
    project = Project(
        code="DEMO-2026",
        name="Proyecto Integrador Demo",
        description="Proyecto demo para la asignatura Gestión de Proyectos de Software.",
        objectives="Demostrar cronograma, costos, KPI y gestión del cambio.",
        director_id=admin.id,
        sponsor="Universidad Demo",
        authorized_budget=Decimal(125000),
        planned_start=date(2026, 1, 5),
        planned_end=date(2026, 4, 30),
        status="en_ejecucion",
    )
    db.session.add(project)
    db.session.flush()
    db.session.add_all(
        [
            ProjectMembership(project_id=project.id, user_id=admin.id, membership_role="manager"),
            ProjectMembership(project_id=project.id, user_id=member.id, membership_role="member"),
        ]
    )
    stages = ("Inicio", "Planificación", "Ejecución", "Cierre")
    tasks: list[Task] = []
    for index in range(32):
        start = date(2026, 1, 5) + timedelta(days=index * 2)
        tasks.append(
            Task(
                project_id=project.id,
                responsible_id=member.id,
                name=f"Tarea demo {index + 1:02d}",
                description="Tarea plana de demostración.",
                etapa=stages[index // 8],
                planned_start=start,
                planned_end=start + timedelta(days=2),
                planned_duration_days=3,
                progress_percent=Decimal((index % 11) * 10),
            )
        )
    db.session.add_all(tasks)
    db.session.flush()
    dependency_types = ("FS", "SS", "FF", "SF")
    for index, dependency_type in enumerate(dependency_types):
        db.session.add(
            TaskDependency(
                predecessor_id=tasks[index].id,
                successor_id=tasks[index + 1].id,
                dependency_type=dependency_type,
                lag_days=index - 1,
            )
        )
    resources: list[Resource] = []
    for index in range(5):
        resources.append(
            Resource(
                project_id=project.id,
                type="Profesional",
                name=f"Profesional demo {index + 1}",
                specialty=("Análisis", "Desarrollo", "QA", "UX", "DevOps")[index],
                hourly_rate=Decimal(35 + index * 5),
                hours_per_week=Decimal(40),
                weeks=Decimal(4),
            )
        )
    resources.extend(
        [
            Resource(project_id=project.id, type="Licencia", name="Licencia demo", quantity=Decimal(5), unit_cost=Decimal(100)),
            Resource(project_id=project.id, type="Material", name="Material demo", quantity=Decimal(20), unit_cost=Decimal(15)),
            Resource(project_id=project.id, type="Equipamiento", name="Equipamiento demo", quantity=Decimal(2), unit_cost=Decimal(800)),
            Resource(project_id=project.id, type="Otros", name="Otros demo", quantity=Decimal(1), unit_cost=Decimal(250)),
        ]
    )
    db.session.add_all(resources)
    db.session.flush()
    for index, resource in enumerate(resources):
        db.session.add(
            TaskResourceAssignment(
                task_id=tasks[index % len(tasks)].id,
                resource_id=resource.id,
                planned_units=Decimal(1),
                actual_units=Decimal("0.5"),
            )
        )
    for index in range(6):
        db.session.add(
            Milestone(
                project_id=project.id,
                name=f"Hito demo {index + 1}",
                committed_date=date(2026, 1, 30) + timedelta(days=index * 20),
                status="cumplido" if index < 2 else "pendiente",
                acceptance_criteria="Criterios demo verificables.",
                evidence="https://example.invalid/evidencia-demo",
            )
        )
    db.session.flush()
    milestones = list(
        db.session.scalars(
            select(Milestone).where(Milestone.project_id == project.id)
        )
    )
    for index, milestone in enumerate(milestones):
        milestone.tasks.append(tasks[index * 5])
    for index in range(8):
        db.session.add(
            KpiDefinition(
                project_id=project.id,
                code=f"PRJ-{index + 1:02d}",
                name=f"KPI proyecto demo {index + 1}",
                scope="project" if index < 6 else "milestone",
                variables=["trabajo_completado", "trabajo_total"],
                formula="trabajo_completado / trabajo_total * 100",
                unit="%",
                target=Decimal(80),
                direction="higher",
                thresholds={"green": 80, "yellow": 50},
                source="automatic",
                periodicity="manual",
            )
        )
    db.session.flush()
    project_kpis = list(
            db.session.scalars(
                select(KpiDefinition).where(
                    KpiDefinition.project_id == project.id,
                    KpiDefinition.scope.in_(("project", "milestone")),
                )
            )
    )
    for index, milestone in enumerate(milestones):
        milestone.kpis.append(project_kpis[index % len(project_kpis)])
    change_types = ("alcance", "tiempo", "costo", "recurso", "tecnologia")
    for index in range(5):
        db.session.add(
            ChangeRequest(
                project_id=project.id,
                change_code=f"CH-{index + 1:02d}",
                requester_id=member.id,
                description=f"Solicitud de cambio demo {index + 1}.",
                justification="Justificación académica.",
                change_type=change_types[index],
                priority=("baja", "media", "alta", "critica", "media")[index],
                risk=("bajo", "medio", "alto", "critico", "medio")[index],
                impact={"budget_delta": str(index * 100)},
                stage=("Registro", "Evaluación de impacto", "Decisión", "Implementación", "Seguimiento de adopción")[index],
                status="pending",
                estimated_cost=Decimal(index * 100),
            )
        )
    for index in range(12):
        db.session.add(
            KpiDefinition(
                project_id=project.id,
                code=f"CHG-{index + 1:02d}",
                name=f"KPI cambio demo {index + 1}",
                scope="change",
                variables=["cambios_aprobados", "cambios_totales"],
                formula="cambios_aprobados / cambios_totales * 100",
                unit="%",
                target=Decimal(80),
                direction="higher",
                thresholds={"green": 80, "yellow": 50},
                source="automatic",
                periodicity="manual",
            )
        )
    db.session.commit()
    return admin_password, user_password


def register_cli(app) -> None:
    """Registra el comando Flask `seed-demo`."""
    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Carga datos de demostración y muestra credenciales aleatorias."""
        with app.app_context():
            try:
                admin_password, user_password = seed_demo()
            except RuntimeError as error:
                raise click.ClickException(str(error)) from error
            print("Demo creada.")
            print(f"admin.demo@example.invalid / {admin_password}")
            print(f"usuario.demo@example.invalid / {user_password}")
