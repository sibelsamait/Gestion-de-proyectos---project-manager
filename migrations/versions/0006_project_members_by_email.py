"""Registro con empresa y lista de usuarios por proyecto identificada por correo."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "0006_project_members_by_email"
down_revision = "0005_simple_login_and_audit"
branch_labels = None
depends_on = None

ROLE_FROM_MEMBERSHIP = {"manager": "gestor", "member": "miembro"}
MEMBERSHIP_FROM_ROLE = {"admin": "manager", "gestor": "manager", "miembro": "member"}


def upgrade() -> None:
    """Crea `project_members`, traspasa directores y membresías, y elimina la tabla anterior."""
    bind = op.get_bind()
    op.add_column("users", sa.Column("company", sa.String(160), nullable=True))

    project_role = sa.Enum("admin", "gestor", "miembro", name="project_role", create_type=False)
    project_role.create(bind, checkfirst=True)
    members = op.create_table(
        "project_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("role", project_role, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "email", name="uq_project_member_email"),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_email", "project_members", ["email"])

    # Traspaso: director -> admin; manager -> gestor; member -> miembro.
    rows: dict[tuple[str, str], str] = {}
    for project_id, email in bind.execute(sa.text(
        "SELECT p.id, u.email FROM projects p JOIN users u ON u.id = p.director_id"
    )):
        rows[(project_id, email.strip().lower())] = "admin"
    for project_id, email, role in bind.execute(sa.text(
        "SELECT m.project_id, u.email, CAST(m.membership_role AS VARCHAR(20)) "
        "FROM project_memberships m JOIN users u ON u.id = m.user_id"
    )):
        rows.setdefault((project_id, email.strip().lower()), ROLE_FROM_MEMBERSHIP.get(role, "miembro"))
    # Ningún proyecto queda sin administrador: se asignan los administradores globales.
    global_admins = [email.strip().lower() for (email,) in bind.execute(sa.text(
        "SELECT email FROM users WHERE CAST(role AS VARCHAR(20)) = 'admin'"
    ))]
    for (project_id,) in bind.execute(sa.text("SELECT id FROM projects")):
        if not any(pid == project_id and role == "admin" for (pid, _), role in rows.items()):
            for email in global_admins:
                rows[(project_id, email)] = "admin"
    now = datetime.now(UTC)
    if rows:
        op.bulk_insert(members, [
            {"id": str(uuid4()), "project_id": pid, "email": email, "role": role, "added_at": now}
            for (pid, email), role in rows.items()
        ])

    op.drop_table("project_memberships")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS membership_role")


def downgrade() -> None:
    """Restaura `project_memberships` solo para correos ya registrados."""
    bind = op.get_bind()
    membership_role = sa.Enum("member", "manager", name="membership_role", create_type=False)
    membership_role.create(bind, checkfirst=True)
    memberships = op.create_table(
        "project_memberships",
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("membership_role", membership_role, nullable=False),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_member"),
    )
    restored = [
        {"project_id": pid, "user_id": uid, "membership_role": MEMBERSHIP_FROM_ROLE[role]}
        for pid, uid, role in bind.execute(sa.text(
            "SELECT m.project_id, u.id, CAST(m.role AS VARCHAR(20)) "
            "FROM project_members m JOIN users u ON lower(u.email) = m.email"
        ))
    ]
    if restored:
        op.bulk_insert(memberships, restored)
    op.drop_index("ix_project_members_email", table_name="project_members")
    op.drop_index("ix_project_members_project_id", table_name="project_members")
    op.drop_table("project_members")
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS project_role")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("company")
