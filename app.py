# app.py
import os
import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_migrate import Migrate
from sqlalchemy import func

from models import db
from models.user import User
from models.client import Client
from models.solar_user import SolarUser, SolarLoginCode

from routes.solar_system import solar_system_bp
from routes.journal_api import bp_journal
from utils.mailer import send_contact_email
from routes.admin_command_center import admin_command_center_bp
from utils.command_center import get_service_state, SERVICES

def handle_contact(data: dict) -> None:
	print(f"[CONTACT {datetime.datetime.utcnow().isoformat()}] {data}")


def admin_required(fn):
	from functools import wraps

	@wraps(fn)
	def wrapper(*args, **kwargs):
		if not current_user.is_authenticated:
			return redirect(url_for("login"))
		role = getattr(current_user, "role", None)
		if role == "admin":
			return fn(*args, **kwargs)
		if role == "client":
			return redirect(url_for("client_dashboard"))
		return redirect(url_for("index"))

	return wrapper


def create_app():
	app = Flask(__name__)

	# --------------------------------------------------
	# config
	# --------------------------------------------------

	app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-fallback-change-me")
	app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///hapitech.db")
	app.config["SQLALCHEMY_BINDS"] = {
		"solar": os.getenv("SOLAR_DATABASE_URL", "sqlite:///solar_journal.db")
	}
	app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

	# Hard ceiling on any request body at all — rejects oversized uploads before
	# Flask even fully reads them into memory. A little headroom over the 15MB
	# raw-image limit to allow for the other multipart form fields.
	app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

	# --------------------------------------------------
	# extensions
	# --------------------------------------------------
	db.init_app(app)
	migrate = Migrate(app, db)

	# --------------------------------------------------
	# make sure both non-migration-managed databases exist —
	# both of these are safe to call every startup: SQLAlchemy's
	# create_all only creates missing tables, and init_db uses
	# CREATE TABLE IF NOT EXISTS. This is what closes the recurring
	# "no such table" issue for good on any fresh environment.
	# --------------------------------------------------
	with app.app_context():
		db.create_all(bind_key="solar")

		# create_all only creates missing tables — it never alters existing
		# ones. solar_journal_entries already existed before entity_kind/
		# entity_name were added, so patch those in safely if missing.
		from sqlalchemy import inspect, text
		inspector = inspect(db.engines["solar"])
		if "solar_journal_entries" in inspector.get_table_names():
			existing_cols = {c["name"] for c in inspector.get_columns("solar_journal_entries")}
			with db.engines["solar"].begin() as conn:
				if "entity_kind" not in existing_cols:
					conn.execute(text(
						"ALTER TABLE solar_journal_entries ADD COLUMN entity_kind VARCHAR(20) NOT NULL DEFAULT 'general'"
					))
				if "entity_name" not in existing_cols:
					conn.execute(text(
						"ALTER TABLE solar_journal_entries ADD COLUMN entity_name VARCHAR(80) NOT NULL DEFAULT 'General'"
					))
				if "is_public" not in existing_cols:
					conn.execute(text(
						"ALTER TABLE solar_journal_entries ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT 0"
					))

		if "solar_users" in inspector.get_table_names():
			existing_user_cols = {c["name"] for c in inspector.get_columns("solar_users")}
			with db.engines["solar"].begin() as conn:
				if "exploration_points" not in existing_user_cols:
					conn.execute(text(
						"ALTER TABLE solar_users ADD COLUMN exploration_points INTEGER NOT NULL DEFAULT 0"
					))
				if "scanned_bodies" not in existing_user_cols:
					conn.execute(text(
						"ALTER TABLE solar_users ADD COLUMN scanned_bodies TEXT NOT NULL DEFAULT '[]'"
					))

		from utils.journal_db import init_db as init_journal_db
		init_journal_db()

	login_manager = LoginManager()
	login_manager.login_view = "login"
	login_manager.blueprint_login_views = {
		"solar_system": "solar_system.login"
	}
	login_manager.init_app(app)

	@login_manager.user_loader
	def load_user(user_id):
		if user_id.startswith("solar-"):
			return SolarUser.query.get(int(user_id.split("-", 1)[1]))
		return User.query.get(int(user_id))

	# --------------------------------------------------
	# blueprints
	# --------------------------------------------------
	app.register_blueprint(solar_system_bp, url_prefix="/solar-system")
	app.register_blueprint(bp_journal)
	app.register_blueprint(admin_command_center_bp)

	# --------------------------------------------------
	# error handling — API-style routes get JSON, not an HTML error page
	# (otherwise a crash here breaks every fetch()'s res.json() on the frontend
	# with a confusing "unexpected character" SyntaxError instead of a real message)
	# --------------------------------------------------
	API_PATH_PREFIXES = ("/solar-system/auth/", "/solar-system/profile", "/api/")

	def _wants_json():
		return request.path.startswith(API_PATH_PREFIXES)

	@app.errorhandler(500)
	def handle_500(e):
		if _wants_json():
			return jsonify({"success": False, "message": "Something went wrong on our end. Please try again shortly."}), 500
		return e.get_response() if hasattr(e, "get_response") else (str(e), 500)

	@app.errorhandler(404)
	def handle_404(e):
		if _wants_json():
			return jsonify({"success": False, "message": "Not found."}), 404
		return e.get_response()

	# --------------------------------------------------
	# routes
	# --------------------------------------------------
	@app.route("/")
	def index():
		role = getattr(current_user, "role", None)
		if current_user.is_authenticated and role in ("admin", "client"):
			return redirect(url_for("admin_dashboard" if role == "admin" else "client_dashboard"))
		return render_template("home.html", current_year=datetime.datetime.utcnow().year)

	@app.route("/login", methods=["GET", "POST"])
	def login():
		if request.method == "POST":
			data = request.get_json(silent=True) or {}
			username = (data.get("username") or "").strip()
			password = data.get("password") or ""

			user = User.query.filter_by(username=username).first()
			if user and user.check_password(password):
				login_user(user)
				return jsonify({
					"success": True,
					"message": "Logged in",
					"role": user.role
				})

			return jsonify({
				"success": False,
				"message": "Invalid username or password"
			}), 401

		return render_template("login.html")

	@app.route("/logout", methods=["POST"])
	@login_required
	def logout():
		logout_user()
		return jsonify({"success": True})

	@app.route("/privacy")
	def privacy():
		return render_template("privacy.html", current_year=datetime.datetime.utcnow().year)

	@app.route("/terms")
	def terms():
		return render_template("terms.html", current_year=datetime.datetime.utcnow().year)

	@app.route("/contact", methods=["POST"])
	def contact():
		data = request.get_json(silent=True) or {}
		name = (data.get("name") or "").strip()
		email = (data.get("email") or "").strip()
		message = (data.get("message") or "").strip()
		client = (data.get("client") or "").strip()

		if not (name and email and message):
			return jsonify({"success": False, "message": "All fields required"}), 400

		meta = {
			"client": client,
			"host": request.host,
			"ip": request.headers.get("X-Forwarded-For", request.remote_addr),
			"ua": request.headers.get("User-Agent", ""),
			"referer": request.headers.get("Referer", ""),
			"utc": datetime.datetime.utcnow().isoformat(),
		}

		try:
			send_contact_email(name=name, email=email, message=message, meta=meta)
		except Exception as e:
			# log server-side; return generic error to user
			print(f"[CONTACT_EMAIL_ERROR] {e}")
			return jsonify({"success": False, "message": "Could not send right now. Try again shortly."}), 500

		return jsonify({"success": True, "message": "Sent — we’ll get back to you shortly."})


	@app.route("/dashboard")
	@login_required
	def client_dashboard():
		return render_template("client/dashboard.html")

	@app.route("/admin")
	@admin_required
	def admin_dashboard():
		clients_total = db.session.query(func.count(Client.id)).scalar() or 0
		clients_active = db.session.query(func.count(Client.id)).filter(Client.status == "active").scalar() or 0
		clients_paused = db.session.query(func.count(Client.id)).filter(Client.status == "paused").scalar() or 0
		clients_archived = db.session.query(func.count(Client.id)).filter(Client.status == "archived").scalar() or 0

		users_total = db.session.query(func.count(User.id)).scalar() or 0
		users_admins = db.session.query(func.count(User.id)).filter(User.role == "admin").scalar() or 0
		users_clients = db.session.query(func.count(User.id)).filter(User.role == "client").scalar() or 0

		stats = {
			"clients_total": clients_total,
			"clients_active": clients_active,
			"clients_paused": clients_paused,
			"clients_archived": clients_archived,
			"users_total": users_total,
			"users_admins": users_admins,
			"users_clients": users_clients,
			"invoices_total": 0,
			"invoices_unpaid": 0,
			"invoices_overdue": 0,
			"alerts_total": 0
		}

		# operations: service health cards
		service_states = [get_service_state(svc) for svc in SERVICES.values()]

		recent_clients = Client.query.order_by(Client.id.desc()).limit(5).all()

		return render_template(
			"admin/dashboard.html",
			stats=stats,
			recent_clients=recent_clients,
			service_states=service_states,
		)

	@app.route("/admin/clients")
	@admin_required
	def admin_clients():
		clients = Client.query.order_by(Client.name.asc()).all()
		return render_template("admin/clients/index.html", clients=clients)

	@app.route("/admin/clients/new", methods=["GET", "POST"])
	@admin_required
	def admin_clients_new():
		if request.method == "POST":
			form = request.form
			c = Client(
				name=(form.get("name") or "").strip(),
				primary_email=(form.get("primary_email") or "").strip() or None,
				phone=(form.get("phone") or "").strip() or None,
				status=form.get("status") or "active"
			)
			db.session.add(c)
			db.session.commit()
			return redirect(url_for("admin_clients"))

		return render_template("admin/clients/new.html")

	@app.route("/admin/clients/<int:client_id>")
	@admin_required
	def admin_clients_view(client_id):
		client = Client.query.get_or_404(client_id)
		return render_template("admin/clients/view.html", client=client)

	@app.route("/admin/clients/<int:client_id>/edit", methods=["GET", "POST"])
	@admin_required
	def admin_clients_edit(client_id):
		client = Client.query.get_or_404(client_id)

		if request.method == "POST":
			form = request.form
			client.name = (form.get("name") or "").strip()
			client.primary_email = (form.get("primary_email") or "").strip() or None
			client.phone = (form.get("phone") or "").strip() or None
			client.status = (form.get("status") or "active")
			db.session.commit()
			return redirect(url_for("admin_clients_view", client_id=client.id))

		return render_template("admin/clients/edit.html", client=client)

	return app

app = create_app()

if __name__ == "__main__":
	app.run(debug=True, host="0.0.0.0", port=5000)