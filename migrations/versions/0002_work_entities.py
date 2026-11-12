"""Entidades funcionales de proyectos, tareas, recursos e hitos."""

import sqlalchemy as sa
from alembic import op

revision = "0002_work_entities"
down_revision = "0001_identity_and_authorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Agrega las tablas de trabajo de la Fase 2."""
    bind = op.get_bind()
    dependency_type = sa.Enum(
        "FS", "SS", "FF", "SF", name="dependency_type", create_type=False
    )
    resource_type = sa.Enum(
        "Profesional",
        "Licencia",
        "Material",
        "Equipamiento",
        "Otros",
        name="resource_type",
        create_type=False,
    )
    milestone_status = sa.Enum(
        "pendiente",
        "en_progreso",
        "cumplido",
        "vencido",
        name="milestone_status",
        create_type=False,
    )
    for enum in (dependency_type, resource_type, milestone_status):
        enum.create(bind, checkfirst=True)
    op.add_column("projects", sa.Column("authorized_budget", sa.Numeric(14, 2), nullable=False, server_default="0"))
    for name in ("planned_start", "planned_end", "actual_start", "actual_end"):
        op.add_column("projects", sa.Column(name, sa.Date()))
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("etapa", sa.String(120)), sa.Column("planned_start", sa.Date()), sa.Column("planned_end", sa.Date()),
        sa.Column("actual_start", sa.Date()), sa.Column("actual_end", sa.Date()),
        sa.Column("planned_duration_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_duration_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_task_progress"),
    )
    op.create_table(
        "task_dependencies",
        sa.Column("predecessor_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("successor_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("dependency_type", dependency_type, nullable=False),
        sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "non_working_days",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False), sa.Column("reason", sa.String(160)),
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", resource_type, nullable=False), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("specialty", sa.String(120)), sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("hours_per_week", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("weeks", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_table(
        "task_resource_assignments",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("resource_id", sa.String(36), sa.ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("planned_units", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("actual_units", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_table(
        "milestones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("committed_date", sa.Date()), sa.Column("actual_date", sa.Date()),
        sa.Column("status", milestone_status, nullable=False), sa.Column("acceptance_criteria", sa.Text()),
        sa.Column("evidence", sa.Text()),
    )


def downgrade() -> None:
    """Revierte las entidades de Fase 2."""
    for table in ("milestones", "task_resource_assignments", "resources", "non_working_days", "task_dependencies", "tasks"):
        op.drop_table(table)
    for name in ("actual_end", "actual_start", "planned_end", "planned_start", "authorized_budget"):
        op.drop_column("projects", name)
