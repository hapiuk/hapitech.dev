# app.py — HapiTech platform (public site, admin, client portal, reviews, AI news).
# See docs/BUILD_PLAN.md for the architecture and phase history.
import datetime
import os

from dotenv import load_dotenv

load_dotenv()   # .env next to the app (SECRET_KEY, DATABASE_URL, SMTP_*), before anything reads os.environ

from flask import Flask, jsonify, request  # noqa: E402
from flask_login import LoginManager
from flask_migrate import Migrate

from models import db
from models.core import User


def _is_dev() -> bool:
    return os.getenv("FLASK_DEBUG") == "1" or os.getenv("APP_ENV") == "development"


def create_app(test_config: dict | None = None):
    app = Flask(__name__)

    # ---------------------------------------------------------------- config
    secret = os.getenv("SECRET_KEY")
    if not secret:
        if not (_is_dev() or (test_config or {}).get("TESTING")):
            raise RuntimeError("SECRET_KEY is not set. Refusing to start in production without it.")
        secret = "dev-only-not-for-production"
    app.config.update(
        SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///hapitech.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=40 * 1024 * 1024,           # photo uploads (6 x phone photos)
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not _is_dev(),
        REMEMBER_COOKIE_DURATION=datetime.timedelta(days=14),
        REMEMBER_COOKIE_SECURE=not _is_dev(),
        REMEMBER_COOKIE_HTTPONLY=True,
        # links that leave the site (review requests, invites): the live domain in production,
        # whatever host you're browsing in development
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL") or (None if _is_dev() else "https://hapitech.dev"),
        UPLOAD_ROOT=os.getenv("UPLOAD_ROOT", ""),      # default: <instance>/uploads
        MAIL_MODE=os.getenv("MAIL_MODE", "log" if _is_dev() else "smtp"),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["UPLOAD_ROOT"]:
        app.config["UPLOAD_ROOT"] = os.path.join(app.instance_path, "uploads")
    os.makedirs(app.instance_path, exist_ok=True)

    # ---------------------------------------------------------------- extensions
    db.init_app(app)
    Migrate(app, db, render_as_batch=True)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        if not str(user_id).isdigit():          # e.g. stale "solar-…" sessions from the old app
            return None
        return db.session.get(User, int(user_id))

    from utils.security import init_security
    init_security(app)

    # ---------------------------------------------------------------- blueprints
    from routes.public import public_bp
    from routes.auth import auth_bp
    from routes.news import news_bp
    from routes.admin import admin_bp
    from routes.portal import portal_bp
    from routes.reviews_public import reviews_public_bp
    from routes.site_api import site_api_bp
    from routes.lab import lab_bp
    from routes.pwa import pwa_bp
    from routes.customer import customer_bp

    for bp in (pwa_bp, customer_bp, public_bp, auth_bp, news_bp, admin_bp, portal_bp, reviews_public_bp, site_api_bp, lab_bp):
        app.register_blueprint(bp)

    from cli import register_cli
    register_cli(app)

    from utils.templating import init_templating
    init_templating(app)

    from utils.tasks import maybe_run

    @app.before_request
    def _background_tasks():
        maybe_run(app)

    # ---------------------------------------------------------------- errors
    JSON_PREFIXES = ("/api/", "/auth/", "/admin/api/", "/portal/api/")

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith(JSON_PREFIXES):
            return jsonify({"ok": False, "message": "Not found."}), 404
        return e

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith(JSON_PREFIXES):
            return jsonify({"ok": False, "message": "Something went wrong on our end. Please try again."}), 500
        return e

    return app


# gunicorn on the server loads `app:app`; keep this module-level instance.
app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
