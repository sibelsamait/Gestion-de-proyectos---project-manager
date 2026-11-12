"""Historial de transiciones del flujo de cambios."""

import sqlalchemy as sa
from alembic import op

revision = "0008_change_stage_history"
down_revision = "0007_kpi_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea el historial de etapas de las solicitudes."""
    op.create_table(
        "change_stage_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "change_request_id",
            sa.String(36),
            sa.ForeignKey("change_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_stage", sa.String(50)),
        sa.Column("to_stage", sa.String(50), nullable=False),
        sa.Column(
            "actor_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Elimina el historial de etapas."""
    op.drop_table("change_stage_history")
