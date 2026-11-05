"""Servicio central de auditoría."""

from flask_login import current_user

from ..extensions import db
from ..models import AuditLog


def record_audit(
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """Registra solo metadatos operacionales no sensibles."""
    actor_id = current_user.id if current_user.is_authenticated else None
    event = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata,
    )
    db.session.add(event)
    return event

