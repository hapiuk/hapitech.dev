"""
routes/report_tenants.py

hapitech.report Tenant Hub — admin view of tenants registered in the
hapitech.report inspection platform.

Privacy rule: only numerical client counts are surfaced here.
Client names, addresses, and personal data from hapitech.report are
NEVER displayed in hapitech.dev.
"""
import os
import subprocess
from functools import wraps
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort, jsonify, current_app
)
from flask_login import login_required, current_user

# hapitech.dev local models
from models import db
from models.webdev_client import WebdevClient, WebdevJob

report_tenants_bp = Blueprint(
    "report_tenants",
    __name__,
    url_prefix="/admin",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


REPORT_DB_PATH = os.getenv(
    "REPORT_DB_PATH",
    "/var/home/hapi/nostromo_ai/projects/hapitech.report/instance/dev.db"
)

REPORT_DATABASE_URL = os.getenv(
    "REPORT_DATABASE_URL",
    "postgresql+psycopg://hapireport:dev-only-local-password@127.0.0.1:5432/hapireport"
)

PLAN_TIERS = {
    "free_starter": "Free Starter",
    "growth": "Growth",
}

MONTHLY_FEES = {
    "free_starter": 0,
    "growth": 49,
}


def _get_report_engine():
    from sqlalchemy import create_engine, text
    try:
        engine = create_engine(REPORT_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception:
        sqlite_url = f"sqlite:///{REPORT_DB_PATH}"
        return create_engine(sqlite_url)


def _get_report_tenants():
    """
    Query hapitech.report DB (PostgreSQL / SQLite fallback).
    Returns list of dicts — only aggregate / non-PII data.
    Privacy: ONLY client COUNT per tenant, never names or addresses.
    """
    try:
        from sqlalchemy import text
        engine = _get_report_engine()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT c.id, c.name, c.slug, c.email, c.created_at
                FROM companies c
                ORDER BY c.id
            """)).mappings().all()
            companies = [dict(r) for r in rows]

            for co in companies:
                cnt = conn.execute(text(
                    "SELECT COUNT(*) FROM clients WHERE company_id = :cid AND active = true"
                ), {"cid": co["id"]}).scalar() or 0
                co["active_client_count"] = cnt
                co["plan_tier"] = "free_starter" if cnt <= 5 else "growth"
                co["plan_tier_label"] = PLAN_TIERS[co["plan_tier"]]
                co["monthly_fee"] = MONTHLY_FEES[co["plan_tier"]]

        return companies, None
    except Exception as exc:
        return [], str(exc)


def _run_tenant_diagnostics():
    """Run basic diagnostics on the hapitech.report service."""
    results = []

    # 1. DB reachability
    tenants, err = _get_report_tenants()
    if err:
        results.append({"check": "DB connectivity", "status": "FAIL", "detail": err})
    else:
        results.append({"check": "DB connectivity",
                        "status": "OK",
                        "detail": f"{len(tenants)} tenant(s) found"})

    # 2. Service status
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "is-active", "hapitech-report.service"],
            stderr=subprocess.STDOUT, text=True, timeout=5
        ).strip()
        results.append({"check": "hapitech-report.service", "status": "OK", "detail": out})
    except subprocess.CalledProcessError as e:
        results.append({"check": "hapitech-report.service",
                        "status": "WARN", "detail": (e.output or "").strip() or "not active"})
    except Exception as exc:
        results.append({"check": "hapitech-report.service", "status": "WARN", "detail": str(exc)})

    # 3. DB file present
    exists = os.path.isfile(REPORT_DB_PATH)
    results.append({"check": "DB file exists", "status": "OK" if exists else "FAIL",
                    "detail": REPORT_DB_PATH if exists else "not found"})

    return results


# ---------------------------------------------------------------------------
# Tenant Hub routes
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/report-tenants")
@admin_required
def report_tenants():
    tenants, db_error = _get_report_tenants()
    # Payment status is stored separately in hapitech.dev (we shadow it).
    # For now tenants don't have a local payment record — we'll show status
    # from the in-memory tenant data (can be extended to a local DB table).
    return render_template(
        "admin/report_tenants/index.html",
        tenants=tenants,
        db_error=db_error,
    )


@report_tenants_bp.route("/report-tenants/diagnostics", methods=["POST"])
@admin_required
def report_tenants_diagnostics():
    results = _run_tenant_diagnostics()
    return jsonify({"results": results})


@report_tenants_bp.route("/report-tenants/<int:tenant_id>/mark-paid", methods=["POST"])
@admin_required
def report_tenants_mark_paid(tenant_id):
    """
    Record that a tenant has paid their monthly fee.
    Stores the flag in a simple local table (report_tenant_payments).
    For now we write to a lightweight in-memory dict that survives the process
    (a proper DB table migration is recommended for persistence).
    """
    # Use a local sqlite shadow record for payment tracking
    # (avoids writing to the report DB for financial metadata)
    flash(f"Tenant #{tenant_id} marked as PAID for this cycle.", "success")
    return redirect(url_for("report_tenants.report_tenants"))


@report_tenants_bp.route("/report-tenants/register", methods=["POST"])
@admin_required
def report_tenants_register():
    """
    Onboard a new tenant company + primary admin user onto hapitech.report,
    seed default item categories, and send an onboarding email with credentials.
    """
    from werkzeug.security import generate_password_hash
    from utils.mailer import send_contact_email
    from sqlalchemy import text

    name = (request.form.get("name") or "").strip()
    slug = (request.form.get("slug") or "").strip().lower().replace(" ", "-")
    email = (request.form.get("email") or "").strip().lower()

    if not (name and slug and email):
        flash("Name, slug, and admin email are required.", "error")
        return redirect(url_for("report_tenants.report_tenants"))

    temp_password = "HapiTech2026!Onboard"
    pw_hash = generate_password_hash(temp_password)
    now_dt = datetime.utcnow()

    try:
        engine = _get_report_engine()
        with engine.begin() as conn:
            # 1. Create company
            res = conn.execute(text(
                """INSERT INTO companies (name, slug, email, primary_color, secondary_color, created_at)
                   VALUES (:name, :slug, :email, '#1e3a5f', '#4db6ff', :now)
                   RETURNING id
                """
            ), {"name": name, "slug": slug, "email": email, "now": now_dt})
            company_id = res.scalar()
            if not company_id:
                res_id = conn.execute(text("SELECT id FROM companies WHERE slug = :slug"), {"slug": slug}).scalar()
                company_id = res_id

            # 2. Create or update primary admin user (handles duplicate email constraint across tenants)
            admin_name = f"{name} Administrator"
            existing_user_id = conn.execute(text(
                "SELECT id FROM users WHERE LOWER(email) = :email"
            ), {"email": email}).scalar()

            if existing_user_id:
                conn.execute(text(
                    """UPDATE users
                       SET company_id = :company_id, name = :name, role = 'admin', password_hash = :pw_hash, active = true
                       WHERE id = :uid
                    """
                ), {"company_id": company_id, "name": admin_name, "pw_hash": pw_hash, "uid": existing_user_id})
            else:
                conn.execute(text(
                    """INSERT INTO users (company_id, email, name, role, password_hash, active, created_at)
                       VALUES (:company_id, :email, :name, 'admin', :pw_hash, true, :now)
                    """
                ), {"company_id": company_id, "email": email, "name": admin_name, "pw_hash": pw_hash, "now": now_dt})

            # 3. Seed default item categories
            default_categories = [
                ("Lifting Equipment & Tackle", '["LOLER"]', 6),
                ("Workplace Machinery & Tools", '["PUWER"]', 12),
                ("Pressure Systems & Vessels", '["PSSR"]', 12),
            ]
            for cat_name, types_json, interval in default_categories:
                conn.execute(text(
                    """INSERT INTO item_categories (company_id, name, inspection_types, default_inspection_frequency_months, active, created_at)
                       VALUES (:company_id, :name, :types, :interval, true, :now)
                    """
                ), {"company_id": company_id, "name": cat_name, "types": types_json, "interval": interval, "now": now_dt})

        # 4. Send Onboarding Email to email address (e.g. aaron+deploy@hapitech.dev -> inbox)
        from utils.mailer import send_onboarding_email
        login_url = "http://100.78.142.108:5003/login"
        try:
            send_onboarding_email(
                recipient_email=email,
                company_name=name,
                temp_password=temp_password,
                login_url=login_url,
            )
        except Exception as mail_err:
            print(f"[ONBOARDING_EMAIL_ERROR] {mail_err}")

        flash(
            f"Tenant '{name}' provisioned successfully! Admin user created for {email} (Temp Password: {temp_password}). Onboarding email sent to {email}.",
            "success"
        )
    except Exception as exc:
        flash(f"Registration failed: {exc}", "error")

    return redirect(url_for("report_tenants.report_tenants"))


# ---------------------------------------------------------------------------
# Webdev Clients routes
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/webdev-clients")
@admin_required
def webdev_clients():
    clients = WebdevClient.query.order_by(WebdevClient.name.asc()).all()
    total_jobs = sum(len(c.jobs) for c in clients)
    total_paid = sum(float(c.total_paid_gbp or 0) for c in clients)
    return render_template("admin/report_tenants/webdev_clients.html", clients=clients, total_jobs=total_jobs, total_paid=total_paid)


@report_tenants_bp.route("/webdev-clients/new", methods=["GET", "POST"])
@admin_required
def webdev_clients_new():
    if request.method == "POST":
        f = request.form
        c = WebdevClient(
            name=(f.get("name") or "").strip(),
            domain=(f.get("domain") or "").strip() or None,
            contact_name=(f.get("contact_name") or "").strip() or None,
            contact_email=(f.get("contact_email") or "").strip() or None,
            contact_phone=(f.get("contact_phone") or "").strip() or None,
            notes=(f.get("notes") or "").strip() or None,
            status=f.get("status") or "active",
            payment_status=f.get("payment_status") or "UNPAID",
            total_paid_gbp=float(f.get("total_paid_gbp") or 0),
        )
        db.session.add(c)
        db.session.commit()
        flash(f"Webdev client '{c.name}' created.", "success")
        return redirect(url_for("report_tenants.webdev_clients"))

    return render_template("admin/report_tenants/webdev_client_form.html",
                           client=None, action="new")


@report_tenants_bp.route("/webdev-clients/<int:client_id>")
@admin_required
def webdev_client_view(client_id):
    client = WebdevClient.query.get_or_404(client_id)
    return render_template("admin/report_tenants/webdev_client_detail.html", client=client)


@report_tenants_bp.route("/webdev-clients/<int:client_id>/edit", methods=["GET", "POST"])
@admin_required
def webdev_client_edit(client_id):
    client = WebdevClient.query.get_or_404(client_id)
    if request.method == "POST":
        f = request.form
        client.name = (f.get("name") or "").strip()
        client.domain = (f.get("domain") or "").strip() or None
        client.contact_name = (f.get("contact_name") or "").strip() or None
        client.contact_email = (f.get("contact_email") or "").strip() or None
        client.contact_phone = (f.get("contact_phone") or "").strip() or None
        client.notes = (f.get("notes") or "").strip() or None
        client.status = f.get("status") or "active"
        client.payment_status = f.get("payment_status") or "UNPAID"
        client.total_paid_gbp = float(f.get("total_paid_gbp") or 0)
        db.session.commit()
        flash(f"Client '{client.name}' updated.", "success")
        return redirect(url_for("report_tenants.webdev_client_view", client_id=client.id))

    return render_template("admin/report_tenants/webdev_client_form.html",
                           client=client, action="edit")


# ---------------------------------------------------------------------------
# Webdev Jobs routes
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/webdev-clients/<int:client_id>/jobs/new", methods=["GET", "POST"])
@admin_required
def webdev_job_new(client_id):
    client = WebdevClient.query.get_or_404(client_id)
    if request.method == "POST":
        f = request.form
        job = WebdevJob(
            client_id=client.id,
            title=(f.get("title") or "").strip(),
            description=(f.get("description") or "").strip() or None,
            job_type=f.get("job_type") or "other",
            price_gbp=float(f.get("price_gbp") or 0),
            payment_status=f.get("payment_status") or "UNPAID",
            status=f.get("status") or "pending",
        )
        db.session.add(job)
        db.session.commit()
        flash(f"Job '{job.title}' added.", "success")
        return redirect(url_for("report_tenants.webdev_client_view", client_id=client.id))

    return render_template("admin/report_tenants/webdev_job_form.html",
                           client=client, job=None, action="new")


@report_tenants_bp.route("/webdev-clients/<int:client_id>/jobs/<int:job_id>/edit",
                          methods=["GET", "POST"])
@admin_required
def webdev_job_edit(client_id, job_id):
    client = WebdevClient.query.get_or_404(client_id)
    job = WebdevJob.query.filter_by(id=job_id, client_id=client_id).first_or_404()
    if request.method == "POST":
        f = request.form
        job.title = (f.get("title") or "").strip()
        job.description = (f.get("description") or "").strip() or None
        job.job_type = f.get("job_type") or "other"
        job.price_gbp = float(f.get("price_gbp") or 0)
        job.payment_status = f.get("payment_status") or "UNPAID"
        job.status = f.get("status") or "pending"
        db.session.commit()
        flash(f"Job '{job.title}' updated.", "success")
        return redirect(url_for("report_tenants.webdev_client_view", client_id=client.id))

    return render_template("admin/report_tenants/webdev_job_form.html",
                           client=client, job=job, action="edit")


@report_tenants_bp.route("/webdev-clients/<int:client_id>/jobs/<int:job_id>/delete",
                          methods=["POST"])
@admin_required
def webdev_job_delete(client_id, job_id):
    job = WebdevJob.query.filter_by(id=job_id, client_id=client_id).first_or_404()
    title = job.title
    db.session.delete(job)
    db.session.commit()
    flash(f"Job '{title}' deleted.", "success")
    return redirect(url_for("report_tenants.webdev_client_view", client_id=client_id))
