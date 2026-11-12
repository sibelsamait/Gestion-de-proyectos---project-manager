"""Asociaciones de hitos y configuración detallada de recursos."""

import sqlalchemy as sa
from alembic import op

revision = "0006_milestones_resources"
down_revision = "0005_project_recalculation_and_readonly"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Agrega datos específicos de recursos y asociaciones de seguimiento."""
    op.add_column("resources", sa.Column("category", sa.String(120)))
    op.add_column("resources", sa.Column("unit", sa.String(80)))
    op.add_column("resources", sa.Column("period", sa.String(80)))
    op.add_column("resources", sa.Column("daily_max_hours", sa.Numeric(8, 2), nullable=False, server_default="8"))
    op.create_check_constraint(
        "ck_resource_daily_max_hours", "resources", "daily_max_hours > 0"
    )
    op.create_table(
        "milestone_tasks",
        sa.Column("milestone_id", sa.String(36), sa.ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "milestone_kpis",
        sa.Column("milestone_id", sa.String(36), sa.ForeignKey("milestones.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kpi_id", sa.String(36), sa.ForeignKey("kpi_definitions.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    """Revierte asociaciones y datos detallados de recursos."""
    op.drop_table("milestone_kpis")
    op.drop_table("milestone_tasks")
    op.drop_constraint("ck_resource_daily_max_hours", "resources", type_="check")
    for column in ("daily_max_hours", "period", "unit", "category"):
        op.drop_column("resources", column)
