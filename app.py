import os
import re
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template
from sqlalchemy import event

from config import Config
from extensions import csrf, db, login_manager


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    if not app.config.get("TESTING") and not app.config.get("SECRET_KEY"):
        raise RuntimeError("Set SECRET_KEY in the environment or a local .env file.")
    try:
        face_threshold = float(app.config["FACE_DISTANCE_THRESHOLD"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("FACE_DISTANCE_THRESHOLD must be a number between 0 and 1.") from exc
    if not 0 < face_threshold <= 1:
        raise RuntimeError("FACE_DISTANCE_THRESHOLD must be greater than 0 and no more than 1.")
    app.config["FACE_DISTANCE_THRESHOLD"] = face_threshold
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    with app.app_context():
        engine = db.engine
        if engine.dialect.name == "sqlite":
            def enable_sqlite_foreign_keys(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            event.listen(engine, "connect", enable_sqlite_foreign_keys)

    from models import User

    bootstrap_admin_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    bootstrap_admin_name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "").strip()
    bootstrap_admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    bootstrap_values = (bootstrap_admin_email, bootstrap_admin_name, bootstrap_admin_password)
    if any(bootstrap_values):
        if not all(bootstrap_values):
            raise RuntimeError(
                "BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_NAME, and "
                "BOOTSTRAP_ADMIN_PASSWORD must all be configured together."
            )
        if len(bootstrap_admin_password) < 14:
            raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 14 characters.")
        if (
            len(bootstrap_admin_name) > 120
            or len(bootstrap_admin_email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", bootstrap_admin_email)
        ):
            raise RuntimeError("Bootstrap administrator name or email is invalid.")
        if not app.config.get("TESTING"):
            with app.app_context():
                db.create_all()
                existing_admin = User.query.filter_by(role="admin").first()
                if existing_admin is None:
                    if User.query.filter_by(email=bootstrap_admin_email).first():
                        raise RuntimeError("Bootstrap administrator email is already in use.")
                    admin = User(
                        full_name=bootstrap_admin_name[:120],
                        email=bootstrap_admin_email,
                        role="admin",
                    )
                    admin.set_password(bootstrap_admin_password)
                    db.session.add(admin)
                    db.session.commit()
                    app.logger.warning(
                        "Created the one-time bootstrap administrator. Remove "
                        "BOOTSTRAP_ADMIN_* variables from the deployment environment."
                    )
                else:
                    app.logger.info(
                        "An administrator already exists; bootstrap credentials were not used."
                    )

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    from admin import bp as admin_bp
    from auth import bp as auth_bp
    from results import bp as results_bp
    from voter import bp as voter_bp
    from voting import bp as voting_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(voter_bp)
    app.register_blueprint(voting_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(results_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.context_processor
    def template_context():
        return {"current_year": datetime.now().year}

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "font-src 'self' https://cdn.jsdelivr.net data:; connect-src 'self'",
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def request_too_large(_error):
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.cli.command("init-db")
    def init_db_command():
        """Create database tables for this prototype."""
        with app.app_context():
            db.create_all()
        print("Database tables created.")

    @app.cli.command("create-admin")
    def create_admin_command():
        """Interactively create an administrator in development mode."""
        import click

        if not app.debug and not app.testing:
            raise click.ClickException("This bootstrap command is development-only; enable FLASK_DEBUG.")
        email = click.prompt("Administrator email").strip().lower()
        name = click.prompt("Administrator full name").strip()
        password = click.prompt("Administrator password", hide_input=True, confirmation_prompt=True)
        if len(password) < 14:
            raise click.ClickException("Administrator password must contain at least 14 characters.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("That email address already exists.")
        admin = User(full_name=name, email=email, role="admin", voter_id=None)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo("Administrator account created.")

    @app.cli.command("generate-face-key")
    def generate_face_key_command():
        """Print a new Fernet key; store it privately in FACE_DATA_KEY."""
        from cryptography.fernet import Fernet

        print(Fernet.generate_key().decode("ascii"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
