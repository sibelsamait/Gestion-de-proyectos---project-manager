"""Datos demo reproducibles en estructura, con credenciales aleatorias."""

import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import click
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CashFlow,
    ChangeRequest,
    KpiDefinition,
    Milestone,
    PreinvestmentStudy,
    Project,
    ProjectMember,
    Resource,
    Risk,
    Task,
    TaskDependency,
    TaskResourceAssignment,
    User,
)
from app.services.planning import apply_scope_template


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
    admin.password = admin_password
    member = User(
        name="Usuario Proyecto Demo",
        email="usuario.demo@example.invalid",
        role="usuario_proyecto",
        terms_accepted_at=datetime.now(UTC),
    )
    member.password = user_password
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
        phase="inversion",
        authorized_by="Comité de Inversiones",
        authorization_date=date(2025, 12, 15),
        authorization_reference="Acta CI-2025-041",
        control_plan=(
            "Reporte semanal de avance y valor ganado (CPI y SPI). Alerta si CPI o SPI bajan de 0,9 "
            "o si un riesgo alto se materializa. Revisión mensual con el patrocinador."
        ),
        discount_rate=Decimal(12),
        evaluation_years=4,
    )
    db.session.add(project)
    db.session.flush()
    db.session.add_all(
        [
            ProjectMember(project_id=project.id, email=admin.email, role="admin"),
            ProjectMember(project_id=project.id, email=member.email, role="gestor"),
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
                # Costo real algo distinto al plan, para que el valor ganado sea ilustrativo.
                actual_units=Decimal(("0.80", "1.10", "0.50", "1.25", "0.95")[index % 5]),
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
    _seed_planning(project.id, admin.id, member.id)
    db.session.commit()
    return admin_password, user_password


def _seed_planning(project_id: str, manager_id: str, lead_id: str) -> None:
    """Estudios, evaluación económica, alcance y riesgos de la demo."""
    conclusions = {
        "mercado": "Demanda validada con 12 entrevistas a clientes objetivo.",
        "tecnico": "Arquitectura web con Flask y PostgreSQL; sin dependencias críticas.",
        "organizacional": "Equipo de cinco profesionales con gerente y jefe de proyecto.",
        "legal": "Cumple la Ley 19.628 de protección de datos personales.",
        "financiero": "VAN positivo a una tasa del 12 %; recuperación antes del tercer año.",
    }
    db.session.add_all(
        PreinvestmentStudy(project_id=project_id, study_type=kind, status="completado", conclusion=text)
        for kind, text in conclusions.items()
    )
    flows = [(120000, 0, 0), (0, 70000, 15000), (0, 85000, 18000), (0, 90000, 20000), (0, 95000, 22000)]
    db.session.add_all(
        CashFlow(project_id=project_id, period=period, investment=Decimal(inv), income=Decimal(inc), costs=Decimal(cost))
        for period, (inv, inc, cost) in enumerate(flows)
    )
    apply_scope_template(db.session, project_id, "software_a_medida")
    db.session.add_all([
        Risk(project_id=project_id, description="Rotación de desarrolladores clave durante la ejecución.",
             category="Recursos humanos", probability=3, impact=4, response="mitigar",
             response_plan="Documentar decisiones y hacer revisiones de código cruzadas.", owner_id=manager_id,
             status="en_tratamiento"),
        Risk(project_id=project_id, description="Cambios de requisitos tardíos por parte del cliente.",
             category="Negocio", probability=4, impact=4, response="mitigar",
             response_plan="Aplicar el flujo formal de solicitudes de cambio con evaluación de impacto.",
             owner_id=lead_id, status="identificado"),
        Risk(project_id=project_id, description="Retraso del proveedor de infraestructura en la nube.",
             category="Proveedor", probability=2, impact=3, response="transferir",
             response_plan="Cláusula de nivel de servicio con multa en el contrato.", owner_id=manager_id),
        Risk(project_id=project_id, description="Sobrecosto por subestimación del esfuerzo de pruebas.",
             category="Costo", probability=3, impact=3, response="aceptar", status="identificado"),
    ])


def register_cli(app) -> None:
    """Registra el comando Flask `seed-demo`."""
    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        """Carga el proyecto de demostración y muestra las contraseñas de sus usuarios."""
        with app.app_context():
            try:
                admin_password, user_password = seed_demo()
            except RuntimeError as error:
                raise click.ClickException(str(error)) from error
            print("Demo creada: proyecto DEMO-2026.")
            print(f"admin.demo@example.invalid / {admin_password}")
            print(f"usuario.demo@example.invalid / {user_password}")
