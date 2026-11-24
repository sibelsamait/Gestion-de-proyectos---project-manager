"""Extensiones Flask inicializadas sin acoplarse a la aplicación."""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
