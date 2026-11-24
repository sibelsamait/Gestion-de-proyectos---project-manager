"""Preinversión, alcance y riesgos del proyecto."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db

STUDY_TYPES = ("mercado", "tecnico", "organizacional", "legal", "financiero")
SCOPE_CATEGORIES = (
    "requisito_funcional",
    "requisito_no_funcional",
    "entregable",
    "exclusion",
    "supuesto",
    "restriccion",
)
RISK_RESPONSES = ("evitar", "mitigar", "transferir", "aceptar")
RISK_STATUSES = ("identificado", "en_tratamiento", "cerrado", "materializado")


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class PreinvestmentStudy(db.Model):
    """Estudio previo de la etapa de preinversión (mercado, técnico, organizacional, legal, financiero)."""

    __tablename__ = "preinvestment_studies"
    __table_args__ = (UniqueConstraint("project_id", "study_type", name="uq_study_project_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    study_type: Mapped[str] = mapped_column(Enum(*STUDY_TYPES, name="study_type"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pendiente", "en_curso", "completado", name="study_status"), nullable=False, default="pendiente"
    )
    conclusion: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class CashFlow(db.Model):
    """Flujo de caja proyectado de un período (año 0 = inversión inicial)."""

    __tablename__ = "cash_flows"
    __table_args__ = (
        UniqueConstraint("project_id", "period", name="uq_cash_flow_period"),
        CheckConstraint("period >= 0", name="ck_cash_flow_period"),
        CheckConstraint("investment >= 0 AND income >= 0 AND costs >= 0", name="ck_cash_flow_amounts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    investment: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    income: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    costs: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)


class ScopeItem(db.Model):
    """Elemento del enunciado de alcance: lo incluido (requisitos, entregables) y lo excluido."""

    __tablename__ = "scope_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(Enum(*SCOPE_CATEGORIES, name="scope_category"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class Risk(db.Model):
    """Factor que podría hacer fracasar el proyecto, con su evaluación y respuesta."""

    __tablename__ = "risks"
    __table_args__ = (
        CheckConstraint("probability BETWEEN 1 AND 5 AND impact BETWEEN 1 AND 5", name="ck_risk_scale"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    response: Mapped[str] = mapped_column(Enum(*RISK_RESPONSES, name="risk_response"), nullable=False, default="mitigar")
    response_plan: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        Enum(*RISK_STATUSES, name="risk_status"), nullable=False, default="identificado"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    @property
    def score(self) -> int:
        """Severidad = probabilidad × impacto (1 a 25)."""
        return self.probability * self.impact

    @property
    def level(self) -> str:
        """Nivel según severidad: bajo ≤4, medio ≤9, alto ≤14, crítico ≥15."""
        score = self.score
        return "bajo" if score <= 4 else "medio" if score <= 9 else "alto" if score <= 14 else "critico"
