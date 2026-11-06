"""Tasas históricas de conversión monetaria."""

import sqlalchemy as sa
from alembic import op

revision = "0004_exchange_rates"
down_revision = "0003_kpis_and_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea el histórico de UF y dólar observado."""
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("indicator", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("value > 0", name="ck_exchange_rate_value_positive"),
        sa.UniqueConstraint("indicator", "rate_date", name="uq_exchange_rate_indicator_date"),
    )
    op.create_index("ix_exchange_rates_indicator", "exchange_rates", ["indicator"])
    op.create_index("ix_exchange_rates_rate_date", "exchange_rates", ["rate_date"])


def downgrade() -> None:
    """Elimina el histórico de tasas."""
    op.drop_index("ix_exchange_rates_rate_date", table_name="exchange_rates")
    op.drop_index("ix_exchange_rates_indicator", table_name="exchange_rates")
    op.drop_table("exchange_rates")
