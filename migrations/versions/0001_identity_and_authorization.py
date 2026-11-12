"""Entidades de identidad, proyectos, membresías y auditoría."""

import sqlalchemy as sa
from alembic import op

revision = "0001_identity_and_authorization"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea las tablas base de Fase 1."""
    user_role = sa.Enum(
        "admin", "usuario_proyecto", name="user_role", create_type=False
    )
    project_status = sa.Enum(
        "planificado",
        "en_ejecucion",
        "suspendido",
        "terminado",
        name="project_status",
        create_type=False,
    )
    membership_role = sa.Enum(
        "member", "manager", name="membership_role", create_type=False
    )
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    project_status.create(bind, checkfirst=True)
    membership_role.create(bind, checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("objectives", sa.Text()),
        sa.Column("director_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("sponsor", sa.String(160)),
        sa.Column("status", project_status, nullable=False),
    )
    op.create_index("ix_projects_code", "projects", ["code"])
    op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("membership_role", membership_role, nullable=False),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON()),
    )
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"])


def downgrade() -> None:
    """Elimina las tablas de identidad en orden de dependencias."""
    op.drop_index("ix_audit_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("project_memberships")
    op.drop_index("ix_projects_code", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    bind = op.get_bind()
    for enum_name in ("membership_role", "project_status", "user_role"):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
