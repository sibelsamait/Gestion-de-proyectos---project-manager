"""Preinversión, autorización, alcance, riesgos y evaluación económica."""

import sqlalchemy as sa
from alembic import op

revision = "0007_planning"
down_revision = "0006_project_members_by_email"
branch_labels = None
depends_on = None

ENUMS = {
    "project_phase": ("preinversion", "inversion"),
    "study_type": ("mercado", "tecnico", "organizacional", "legal", "financiero"),
    "study_status": ("pendiente", "en_curso", "completado"),
    "scope_category": (
        "requisito_funcional", "requisito_no_funcional", "entregable", "exclusion", "supuesto", "restriccion",
    ),
    "risk_response": ("evitar", "mitigar", "transferir", "aceptar"),
    "risk_status": ("identificado", "en_tratamiento", "cerrado", "materializado"),
}


def _enum(name: str) -> sa.Enum:
    return sa.Enum(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    """Crea las tablas de planificación y amplía el proyecto con su ciclo de vida."""
    bind = op.get_bind()
    for name in ENUMS:
        _enum(name).create(bind, checkfirst=True)

    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("phase", _enum("project_phase"), nullable=False, server_default="preinversion"))
        batch.add_column(sa.Column("authorized_by", sa.String(160)))
        batch.add_column(sa.Column("authorization_date", sa.Date()))
        batch.add_column(sa.Column("authorization_reference", sa.String(160)))
        batch.add_column(sa.Column("authorization_notes", sa.Text()))
        batch.add_column(sa.Column("control_plan", sa.Text()))
        batch.add_column(sa.Column("discount_rate", sa.Numeric(6, 3), nullable=False, server_default="10"))
        batch.add_column(sa.Column("evaluation_years", sa.Integer(), nullable=False, server_default="5"))
    # Los proyectos ya en ejecución o terminados se consideran en etapa de inversión.
    op.execute(
        "UPDATE projects SET phase = 'inversion' "
        "WHERE CAST(status AS VARCHAR(20)) IN ('en_ejecucion', 'terminado')"
    )

    op.create_table(
        "preinvestment_studies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("study_type", _enum("study_type"), nullable=False),
        sa.Column("status", _enum("study_status"), nullable=False),
        sa.Column("conclusion", sa.Text()),
        sa.Column("reference", sa.String(300)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "study_type", name="uq_study_project_type"),
    )
    op.create_index("ix_preinvestment_studies_project_id", "preinvestment_studies", ["project_id"])

    op.create_table(
        "cash_flows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("investment", sa.Numeric(16, 2), nullable=False),
        sa.Column("income", sa.Numeric(16, 2), nullable=False),
        sa.Column("costs", sa.Numeric(16, 2), nullable=False),
        sa.UniqueConstraint("project_id", "period", name="uq_cash_flow_period"),
        sa.CheckConstraint("period >= 0", name="ck_cash_flow_period"),
        sa.CheckConstraint("investment >= 0 AND income >= 0 AND costs >= 0", name="ck_cash_flow_amounts"),
    )
    op.create_index("ix_cash_flows_project_id", "cash_flows", ["project_id"])

    op.create_table(
        "scope_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", _enum("scope_category"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scope_items_project_id", "scope_items", ["project_id"])

    op.create_table(
        "risks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(80)),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("impact", sa.Integer(), nullable=False),
        sa.Column("response", _enum("risk_response"), nullable=False),
        sa.Column("response_plan", sa.Text()),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", _enum("risk_status"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("probability BETWEEN 1 AND 5 AND impact BETWEEN 1 AND 5", name="ck_risk_scale"),
    )
    op.create_index("ix_risks_project_id", "risks", ["project_id"])


def downgrade() -> None:
    """Elimina lo agregado; se pierden alcance, riesgos, estudios y flujos."""
    op.drop_index("ix_risks_project_id", table_name="risks")
    op.drop_table("risks")
    op.drop_index("ix_scope_items_project_id", table_name="scope_items")
    op.drop_table("scope_items")
    op.drop_index("ix_cash_flows_project_id", table_name="cash_flows")
    op.drop_table("cash_flows")
    op.drop_index("ix_preinvestment_studies_project_id", table_name="preinvestment_studies")
    op.drop_table("preinvestment_studies")
    with op.batch_alter_table("projects") as batch:
        for column in (
            "evaluation_years", "discount_rate", "control_plan", "authorization_notes",
            "authorization_reference", "authorization_date", "authorized_by", "phase",
        ):
            batch.drop_column(column)
    if op.get_bind().dialect.name == "postgresql":
        for name in ENUMS:
            op.execute(f"DROP TYPE IF EXISTS {name}")
