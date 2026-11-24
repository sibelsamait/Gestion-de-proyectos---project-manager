"""Registro e inicio de sesión simple contra los usuarios de la base de datos."""

from datetime import UTC, datetime

from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select

from ... import validation as v
from ...extensions import db
from ...models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Rutas accesibles sin sesión: login, registro, archivos estáticos y el cron de tasas.
PUBLIC_ENDPOINTS = {"auth.login", "auth.register", "static", "currency.refresh_rates_endpoint"}


@auth_bp.before_app_request
def require_login():
    """Carga el usuario de la sesión y redirige al login si no hay uno."""
    user_id = session.get("user_id")
    g.user = db.session.get(User, user_id) if user_id else None
    if g.user is not None and not g.user.is_active:
        session.pop("user_id", None)
        g.user = None
    if g.user is None and request.endpoint not in PUBLIC_ENDPOINTS:
        if request.path.startswith("/api/"):
            return {"error": "Inicie sesión para continuar."}, 401
        return redirect(url_for("auth.login", next=request.path))
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Acceso concedido si el correo existe y la contraseña coincide con el texto guardado."""
    if g.user is not None:
        return redirect(url_for("projects.dashboard"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = db.session.scalar(select(User).where(User.email == User.normalize_email(email)))
        if user is not None and user.is_active and user.password_matches(password):
            session.clear()
            session["user_id"] = user.id
            target = request.args.get("next", "")
            # Solo rutas internas, para no redirigir a otro sitio.
            if not target.startswith("/") or target.startswith("//"):
                target = url_for("projects.dashboard")
            return redirect(target)
        flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth/login.html", email=email)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Crea una cuenta con correo, nombre, empresa y contraseña repetida, e inicia sesión."""
    if g.user is not None:
        return redirect(url_for("projects.dashboard"))
    if request.method == "POST":
        try:
            address = v.email("email", "El correo")
            name = v.text("name", "El nombre", User.name, required=True)
            company = v.text("company", "La empresa", User.company, required=True)
            password = request.form.get("password", "")
            if not password:
                raise ValueError("La contraseña es obligatoria.")
            if len(password) > 255:
                raise ValueError("La contraseña supera el máximo de 255 caracteres.")
            if password != request.form.get("password_confirmation", ""):
                raise ValueError("Las contraseñas no coinciden.")
            if db.session.scalar(select(User).where(User.email == address)):
                raise ValueError("Ese correo ya está registrado. Inicie sesión.")
            user = User(
                email=address,
                name=name,
                company=company,
                password=password,
                terms_accepted_at=datetime.now(UTC),
            )
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            flash("Cuenta creada. Aquí verá los proyectos en que su correo fue agregado.", "success")
            return redirect(url_for("projects.dashboard"))
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
    return render_template("auth/register.html")


@auth_bp.post("/logout")
def logout():
    """Cierra la sesión."""
    session.clear()
    return redirect(url_for("auth.login"))
