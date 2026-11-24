"""Contraseña en texto plano y auditoría reducida (correo, rol, cambio, descripción, fecha)."""

import sqlalchemy as sa
from alembic import op

revision = "0005_simple_login_and_audit"
down_revision = "0004_exchange_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Renombra la contraseña y reduce la auditoría conservando los eventos existentes."""
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", new_column_name="password", existing_type=sa.String(255),
                           existing_nullable=False)

    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("user_email", sa.String(254), nullable=True))
        batch.add_column(sa.Column("role", sa.String(40), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))

    # Los eventos previos se completan con el correo y rol del actor que los generó.
    op.execute(
        """
        UPDATE audit_log SET
          user_email = COALESCE((SELECT users.email FROM users WHERE users.id = audit_log.actor_id), 'desconocido'),
          role = COALESCE((SELECT CAST(users.role AS VARCHAR(40)) FROM users WHERE users.id = audit_log.actor_id),
                          'desconocido'),
          description = entity_type || ' ' || COALESCE(entity_id, '')
        """
    )

    op.drop_index("ix_audit_entity", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("actor_id")
        batch.drop_column("entity_type")
        batch.drop_column("entity_id")
        batch.drop_column("metadata")
        batch.alter_column("user_email", existing_type=sa.String(254), nullable=False)
        batch.alter_column("role", existing_type=sa.String(40), nullable=False)
        batch.alter_column("description", existing_type=sa.Text(), nullable=False)
    op.create_index("ix_audit_user_time", "audit_log", ["user_email", "occurred_at"])


def downgrade() -> None:
    """Restaura la estructura anterior; los eventos quedan sin actor ni metadatos."""
    op.drop_index("ix_audit_user_time", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        batch.add_column(sa.Column("actor_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("entity_type", sa.String(80), nullable=False, server_default="desconocido"))
        batch.add_column(sa.Column("entity_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("metadata", sa.JSON(), nullable=True))
        batch.drop_column("description")
        batch.drop_column("role")
        batch.drop_column("user_email")
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"])
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password", new_column_name="password_hash", existing_type=sa.String(255),
                           existing_nullable=False)
