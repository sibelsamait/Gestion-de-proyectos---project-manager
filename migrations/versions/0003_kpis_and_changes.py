"""KPI configurables y gestión del cambio."""

import sqlalchemy as sa
from alembic import op

revision = "0003_kpis_and_changes"
down_revision = "0002_work_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea las tablas de la Fase 4."""
    bind = op.get_bind()
    enums = (
        sa.Enum("project", "task", "milestone", "change", name="kpi_scope"),
        sa.Enum("higher", "lower", "range", name="kpi_direction"),
        sa.Enum("automatic", "manual", name="kpi_source"),
    )
    for enum in enums:
        enum.create(bind, checkfirst=True)
    op.create_table(
        "kpi_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text()),
        sa.Column("scope", enums[0], nullable=False),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("formula", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("target", sa.Numeric(14, 4)),
        sa.Column("direction", enums[1], nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("periodicity", sa.String(40), nullable=False),
        sa.Column("source", enums[2], nullable=False),
        sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("result", sa.Numeric(14, 4)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.UniqueConstraint("project_id", "code", name="uq_kpi_project_code"),
    )
    op.create_table(
        "kpi_measurements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kpi_id", sa.String(36), sa.ForeignKey("kpi_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.Numeric(14, 4), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
    )
    op.create_table(
        "change_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_code", sa.String(60), nullable=False),
        sa.Column("requester_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_at", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("risk", sa.String(20), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("committed_date", sa.Date()),
        sa.Column("actual_date", sa.Date()),
        sa.Column("estimated_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("actual_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("result", sa.Text()),
        sa.Column("evidence", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("project_id", "change_code", name="uq_change_project_code"),
    )
    op.create_table(
        "change_baselines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("change_request_id", sa.String(36), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_table(
        "change_applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("change_request_id", sa.String(36), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("attribute", sa.String(80), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=False),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Revierte las entidades de KPI y cambios."""
    for table in ("change_applications", "change_baselines", "change_requests", "kpi_measurements", "kpi_definitions"):
        op.drop_table(table)
    bind = op.get_bind()
    for enum_name in ("kpi_source", "kpi_direction", "kpi_scope"):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
