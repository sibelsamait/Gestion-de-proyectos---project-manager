"""Formularios protegidos con CSRF."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegistrationForm(FlaskForm):
    """Datos mínimos para crear una cuenta."""

    name = StringField("Nombre", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=254)])
    password = PasswordField("Contraseña", validators=[DataRequired(), Length(min=12, max=256)])
    password_confirmation = PasswordField(
        "Repetir contraseña",
        validators=[DataRequired(), EqualTo("password", message="Las contraseñas no coinciden.")],
    )
    accept_terms = BooleanField("Acepto los Términos y la Política de Privacidad", validators=[DataRequired()])
    submit = SubmitField("Registrarme")


class LoginForm(FlaskForm):
    """Credenciales de acceso."""

    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=254)])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    submit = SubmitField("Iniciar sesión")

