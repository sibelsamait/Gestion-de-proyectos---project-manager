"""Autenticación y registro."""

from datetime import UTC, datetime

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from ...extensions import db, limiter
from ...models import User
from ...services.audit import record_audit
from .forms import LoginForm, RegistrationForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register() -> str:
    """Registra una cuenta con consentimiento explícito."""
    if current_user.is_authenticated:
        return redirect(url_for("projects.dashboard"))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        if db.session.scalar(select(User).where(User.email == email)):
            form.email.errors.append("Ese email ya está registrado.")
        else:
            user = User(
                name=form.name.data.strip(),
                email=email,
                terms_accepted_at=datetime.now(UTC),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            record_audit("user.registered", "user", user.id)
            db.session.commit()
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login() -> str:
    """Autentica con mensajes genéricos para no revelar cuentas."""
    if current_user.is_authenticated:
        return redirect(url_for("projects.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        user = db.session.scalar(select(User).where(User.email == email))
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, remember=False, duration=None)
            record_audit("user.login", "user", user.id)
            db.session.commit()
            return redirect(url_for("projects.dashboard"))
        flash("Credenciales inválidas.", "error")
    return render_template("auth/login.html", form=form)


@auth_bp.post("/logout")
def logout() -> str:
    """Cierra la sesión actual."""
    if current_user.is_authenticated:
        record_audit("user.logout", "user", current_user.id)
        db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
