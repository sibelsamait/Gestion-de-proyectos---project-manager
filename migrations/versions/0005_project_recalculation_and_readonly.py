"""Avance calculado del proyecto y rol de solo lectura."""

import sqlalchemy as sa
from alembic import op

revision = "0005_project_recalculation_and_readonly"
down_revision = "0004_exchange_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Agrega el avance persistido y el tercer rol."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'solo_lectura'")
    op.add_column(
        "projects",
        sa.Column("progress_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Revierte el avance; PostgreSQL conserva el valor del enum por seguridad."""
    op.drop_column("projects", "progress_percent")
