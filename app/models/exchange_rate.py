"""Modelo de tasas de cambio históricas."""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


class ExchangeRate(db.Model):
    """Valor CLP de una unidad de UF o USD para una fecha."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("indicator", "rate_date", name="uq_exchange_rate_indicator_date"),
        CheckConstraint("value > 0", name="ck_exchange_rate_value_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    indicator: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
