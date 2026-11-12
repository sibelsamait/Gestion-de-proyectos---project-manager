"""Alertas de cambio de umbral en KPI."""

import sqlalchemy as sa
from alembic import op

revision = "0007_kpi_alerts"
down_revision = "0006_milestones_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea el historial de alertas de KPI."""
    op.create_table(
        "kpi_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "kpi_id",
            sa.String(36),
            sa.ForeignKey("kpi_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "measurement_id",
            sa.String(36),
            sa.ForeignKey("kpi_measurements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(30), nullable=False),
        sa.Column("current_status", sa.String(30), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    """Elimina las alertas de KPI."""
    op.drop_table("kpi_alerts")
