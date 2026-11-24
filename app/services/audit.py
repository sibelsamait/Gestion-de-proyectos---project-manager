"""Auditoría de cambios: correo, rol usado, cambio, descripción y fecha/hora.

Los eventos no se muestran en la interfaz; sirven para medir quién trabajó en la
administración y gestión de cada proyecto.
"""

from flask import g
from sqlalchemy import select

from ..extensions import db
from ..models import AuditLog, Project, ProjectMember


def role_used(project: Project | None) -> str:
    """Rol con el que actuó el usuario en el proyecto (admin, gestor o miembro)."""
    role = g.get("project_role")
    if role is None and project is not None:
        role = db.session.scalar(
            select(ProjectMember.role).where(
                ProjectMember.project_id == project.id, ProjectMember.email == g.user.email
            )
        )
    return role or "sin_rol"


def record_audit(action: str, description: str, project: Project | None = None) -> None:
    """Agrega el evento a la transacción en curso; se guarda junto con el cambio."""
    db.session.add(
        AuditLog(
            user_email=g.user.email,
            role=role_used(project),
            action=action,
            description=f"{project.code} · {description}" if project is not None else description,
        )
    )
