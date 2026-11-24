"""Validación de formularios antes de guardar en la base de datos.

Cada valor se guarda con el tipo, largo y texto exacto que espera el esquema.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import g, request
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute

from .extensions import db
from .models import ProjectMember, User


def column_choices(column: InstrumentedAttribute) -> tuple[str, ...]:
    """Valores permitidos por una columna Enum, tal como están en la base."""
    return tuple(column.property.columns[0].type.enums)


def column_length(column: InstrumentedAttribute) -> int | None:
    """Largo máximo de una columna String; None para Text."""
    return getattr(column.property.columns[0].type, "length", None)


def text(name: str, label: str, column: InstrumentedAttribute | None = None, required: bool = False,
         maximum: int = 5000) -> str | None:
    """Texto recortado; respeta el largo de la columna cuando existe."""
    value = request.form.get(name, "").strip()
    limit = (column_length(column) if column is not None else None) or maximum
    if required and not value:
        raise ValueError(f"{label} es un dato obligatorio.")
    if len(value) > limit:
        raise ValueError(f"{label} supera el máximo de {limit} caracteres.")
    return value or None


def choice(name: str, label: str, column: InstrumentedAttribute, default: str | None = None) -> str:
    """Exige que el valor coincida exactamente con una opción del Enum de la base."""
    value = request.form.get(name, "").strip() or default
    allowed = column_choices(column)
    if value not in allowed:
        raise ValueError(f"{label} debe ser uno de: {', '.join(allowed)}.")
    return value


def iso_date(name: str, label: str) -> date | None:
    """Fecha AAAA-MM-DD o None si el campo viene vacío."""
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} debe usar el formato AAAA-MM-DD.") from exc


def decimal(name: str, label: str, maximum: Decimal | None = None) -> Decimal:
    """Número no negativo sin pasar por float."""
    raw = request.form.get(name, "").strip() or "0"
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{label} debe ser un número válido.") from exc
    if not number.is_finite():
        raise ValueError(f"{label} debe ser un número válido.")
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} no puede superar {maximum}.")
    return number


def integer(name: str, label: str) -> int:
    """Entero no negativo."""
    raw = request.form.get(name, "").strip() or "0"
    try:
        number = int(raw)
    except ValueError as exc:
        raise ValueError(f"{label} debe ser un número entero.") from exc
    if number < 0:
        raise ValueError(f"{label} no puede ser negativo.")
    return number


def user_ref(name: str, label: str, allowed: list[User]) -> str | None:
    """Identificador de una persona de la lista permitida, o None si no se eligió."""
    value = request.form.get(name, "").strip()
    if not value:
        return None
    if value not in {user.id for user in allowed}:
        raise ValueError(f"{label} debe ser un usuario registrado del proyecto.")
    return value


def date_order(start: date | None, end: date | None) -> None:
    """El término no puede preceder al inicio."""
    if start and end and end < start:
        raise ValueError("La fecha de término no puede preceder al inicio.")


def email(name: str, label: str) -> str:
    """Correo normalizado (minúsculas, sin espacios) con forma básica usuario@dominio."""
    value = User.normalize_email(request.form.get(name, ""))
    local, _, domain = value.partition("@")
    if not local or "." not in domain or " " in value or len(value) > 254:
        raise ValueError(f"{label} no es un correo válido.")
    return value


def people(project_id: str | None = None) -> list[User]:
    """Usuarios registrados elegibles: los de la lista del proyecto, o el usuario actual."""
    if project_id is None:
        return [g.user]
    return list(
        db.session.scalars(
            select(User)
            .join(ProjectMember, ProjectMember.email == User.email)
            .where(ProjectMember.project_id == project_id, User.is_active.is_(True))
            .order_by(User.name)
        )
    )
