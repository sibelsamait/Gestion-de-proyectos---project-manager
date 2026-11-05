"""Páginas legales y derechos de privacidad."""

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required, logout_user

from ...extensions import db
from ...services.audit import record_audit
from ...services.privacy import anonymize_user, export_user_data

privacy_bp = Blueprint("privacy", __name__)


@privacy_bp.get("/privacidad")
def privacy_page():
    """Muestra la política editable marcada como borrador."""
    return render_template("legal/privacy.html")


@privacy_bp.get("/terminos")
def terms_page():
    """Muestra los términos editables marcados como borrador."""
    return render_template("legal/terms.html")


@privacy_bp.get("/privacy/export")
@login_required
def export_data():
    """Descarga los datos propios en JSON."""
    return jsonify(export_user_data(current_user))


@privacy_bp.post("/privacy/delete")
@login_required
def delete_account():
    """Anonimiza la cuenta y cierra la sesión."""
    record_audit("user.anonymized", "user", current_user.id)
    anonymize_user(current_user)
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
