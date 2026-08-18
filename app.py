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
from routes.report_tenants import report_tenants_bp
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
	app.register_blueprint(report_tenants_bp)

	# --------------------------------------------------
	# startup DB seeding & admin account setup
	# --------------------------------------------------
	with app.app_context():
		db.create_all()
		admin = User.query.filter((User.email == "aaron@hapitech.dev") | (User.username == "aaron@hapitech.dev") | (User.username == "aaron")).first()
		if not admin:
			admin = User(email="aaron@hapitech.dev", username="aaron@hapitech.dev", role="admin")
			admin.set_password("Password1234!")
			db.session.add(admin)
		else:
			admin.role = "admin"
			admin.email = "aaron@hapitech.dev"
			admin.set_password("Password1234!")
		db.session.commit()

		# Seed initial webdev agency clients if empty
		from models.webdev_client import WebdevClient, WebdevJob
		if not WebdevClient.query.first():
			c1 = WebdevClient(name="Roland's Handyman", domain="rolandshandyman.co.uk", contact_email="aaron@hapitech.dev", payment_status="PAID", total_paid_gbp=500)
			c2 = WebdevClient(name="Ray G's Handyman", domain="rayghandymanservice.co.uk", contact_email="aaron@hapitech.dev", payment_status="PAID", total_paid_gbp=500)
			c3 = WebdevClient(name="Spartan Bricklaying", domain="spartanbricklaying.co.uk", contact_email="aaron@hapitech.dev", payment_status="PAID", total_paid_gbp=750)
			db.session.add_all([c1, c2, c3])
			db.session.flush()

			j1 = WebdevJob(client_id=c1.id, title="Website Build & Launch", job_type="website_build", price_gbp=500, payment_status="PAID", status="completed")
			j2 = WebdevJob(client_id=c2.id, title="Website Build & Launch", job_type="website_build", price_gbp=500, payment_status="PAID", status="completed")
			j3 = WebdevJob(client_id=c3.id, title="Brand Website Build", job_type="website_build", price_gbp=750, payment_status="PAID", status="completed")
			db.session.add_all([j1, j2, j3])
			db.session.commit()

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

			user = User.query.filter((User.username == username) | (User.email == username)).first()
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

	@app.route("/login-code/request", methods=["POST"])
	def request_login_code():
		import random
		from flask import session
		data = request.get_json(silent=True) or {}
		email = (data.get("email") or "").strip().lower()

		if not email:
			return jsonify({"success": False, "message": "Email address required"}), 400

		user = User.query.filter((User.email == email) | (User.username == email)).first()
		if not user:
			# Return generic message to avoid email enumeration
			return jsonify({"success": True, "message": "If an account exists, a code has been sent."})

		code = f"{random.randint(100000, 999999)}"
		session["otp_user_id"] = user.id
		session["otp_code"] = code
		session["otp_expires"] = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat()

		meta = {
			"client": "hapitech.dev admin login",
			"host": request.host,
			"utc": datetime.datetime.utcnow().isoformat(),
		}
		try:
			send_contact_email(
				name="HapiTech Admin System",
				email=user.email,
				message=f"Your HapiTech.dev login verification code is: {code}\n\nThis code expires in 10 minutes.",
				meta=meta,
			)
		except Exception as exc:
			print(f"[OTP_EMAIL_ERROR] {exc}")

		return jsonify({"success": True, "message": "Login code sent to your email address."})

	@app.route("/login-code/verify", methods=["POST"])
	def verify_login_code():
		from flask import session
		data = request.get_json(silent=True) or {}
		code = (data.get("code") or "").strip()

		stored_code = session.get("otp_code")
		user_id = session.get("otp_user_id")
		expires_raw = session.get("otp_expires")

		if not (stored_code and user_id and expires_raw):
			return jsonify({"success": False, "message": "No active login code request found."}), 400

		expires = datetime.datetime.fromisoformat(expires_raw)
		if datetime.datetime.utcnow() > expires:
			session.pop("otp_code", None)
			return jsonify({"success": False, "message": "Login code has expired. Please request a new one."}), 400

		if code != stored_code:
			return jsonify({"success": False, "message": "Invalid code. Please check and try again."}), 400

		user = User.query.get(user_id)
		if not user:
			return jsonify({"success": False, "message": "User account not found."}), 404

		session.pop("otp_code", None)
		session.pop("otp_user_id", None)
		session.pop("otp_expires", None)

		login_user(user)
		return jsonify({"success": True, "message": "Logged in successfully", "role": user.role})

	@app.route("/admin/change-password", methods=["GET", "POST"])
	@admin_required
	def change_password():
		if request.method == "POST":
			data = request.get_json(silent=True) or {}
			current_pw = data.get("current_password") or ""
			new_pw = data.get("new_password") or ""

			if not current_user.check_password(current_pw):
				return jsonify({"success": False, "message": "Current password incorrect."}), 400

			if len(new_pw) < 12:
				return jsonify({"success": False, "message": "New password must be at least 12 characters."}), 400

			current_user.set_password(new_pw)
			db.session.commit()
			return jsonify({"success": True, "message": "Password updated successfully."})

		return render_template("admin/change_password.html")

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
		from models.webdev_client import WebdevClient, WebdevJob
		from routes.report_tenants import _get_report_tenants

		webdev_clients = WebdevClient.query.all()
		webdev_jobs = WebdevJob.query.all()

		total_revenue = sum(float(c.total_paid_gbp) for c in webdev_clients)
		total_received = sum(float(j.price_gbp) for j in webdev_jobs if j.payment_status == "PAID")
		total_unpaid = sum(float(j.price_gbp) for j in webdev_jobs if j.payment_status != "PAID")

		report_tenants, _ = _get_report_tenants()

		stats = {
			"total_revenue": total_revenue,
			"total_received": total_received,
			"total_unpaid": total_unpaid,
			"webdev_clients_count": len(webdev_clients),
			"report_tenants_count": len(report_tenants),
		}

		service_states = [get_service_state(svc) for svc in SERVICES.values()]

		return render_template(
			"admin/dashboard.html",
			stats=stats,
			webdev_clients=webdev_clients,
			webdev_jobs=webdev_jobs,
			report_tenants=report_tenants,
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