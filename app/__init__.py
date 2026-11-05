"""Fábrica de la aplicación Flask."""

from flask import Flask, render_template

from .config import Config
from .extensions import csrf, db, limiter, login_manager, migrate, talisman


def create_app(config_object: type[Config] | Config | None = None) -> Flask:
    """Crea y configura una instancia de Flask."""
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(config_object or Config)
    app.config.from_pyfile("config.py", silent=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    talisman.init_app(
        app,
        content_security_policy=app.config["CONTENT_SECURITY_POLICY"],
        force_https=app.config["TALISMAN_FORCE_HTTPS"],
    )

    from scripts.seed_demo import register_cli

    from . import models  # noqa: F401
    from .blueprints.auth import auth_bp
    from .blueprints.dashboards import dashboards_bp
    from .blueprints.management import management_bp
    from .blueprints.privacy import privacy_bp
    from .blueprints.projects import projects_bp
    from .blueprints.reports import reports_bp
    from .blueprints.work import work_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(management_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(privacy_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(work_bp)
    register_cli(app)

    @app.errorhandler(400)
    def bad_request(error: object) -> tuple[str, int]:
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(error: object) -> tuple[str, int]:
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error: object) -> tuple[str, int]:
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error: object) -> tuple[str, int]:
        return render_template("errors/500.html"), 500

    return app
