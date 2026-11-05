"""Operaciones de derechos del titular."""

from uuid import uuid4

from sqlalchemy import update
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import AuditLog, ChangeRequest, Project, ProjectMembership, Task, User


def export_user_data(user: User) -> dict:
    """Devuelve únicamente datos personales y relaciones propias."""
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "terms_accepted_at": user.terms_accepted_at.isoformat(),
        },
        "projects": [
            {"id": membership.project.id, "code": membership.project.code, "name": membership.project.name}
            for membership in user.memberships
        ],
        "requested_changes": [
            {
                "id": change.id,
                "code": change.change_code,
                "description": change.description,
                "status": change.status,
            }
            for change in db.session.query(ChangeRequest).filter_by(requester_id=user.id)
        ],
    }


def anonymize_user(user: User) -> None:
    """Anonimiza autoría y elimina membresías conservando integridad histórica."""
    anonymous_id = uuid4().hex
    db.session.execute(update(AuditLog).where(AuditLog.actor_id == user.id).values(actor_id=None))
    db.session.execute(update(Task).where(Task.responsible_id == user.id).values(responsible_id=None))
    db.session.execute(update(Project).where(Project.director_id == user.id).values(director_id=None))
    db.session.execute(
        update(ChangeRequest)
        .where(ChangeRequest.responsible_id == user.id)
        .values(responsible_id=None)
    )
    db.session.query(ProjectMembership).filter_by(user_id=user.id).delete()
    user.name = "Usuario anonimizado"
    user.email = f"anon-{anonymous_id}@invalid.local"
    user.password_hash = generate_password_hash(uuid4().hex, method="scrypt")
    user.is_active = False
