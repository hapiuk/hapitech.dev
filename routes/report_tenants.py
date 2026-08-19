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
from models.monthly_payment_status import MonthlyPaymentStatus
from models.pricing_tier import PricingTier

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

def _get_plan_tiers():
    """Load pricing tiers from the database, falling back to defaults if empty."""
    try:
        tiers = PricingTier.query.filter_by(active=True).order_by(
            PricingTier.sort_order.asc()
        ).all()
        if tiers:
            return {t.tier_key: t.name for t in tiers}, {t.tier_key: float(t.monthly_price_gbp) for t in tiers}
    except Exception:
        pass
    # Fallback to hardcoded defaults
    return {
        "free_starter": "Free Starter",
        "standard_25": "Standard 25 Clients",
        "standard_75": "Standard 75 Clients",
        "standard_150": "Standard 150 Clients",
        "standard_300": "Standard 300 Clients",
        "bespoke": "Bespoke (300+)",
    }, {
        "free_starter": 0,
        "standard_25": 79,
        "standard_75": 149,
        "standard_150": 249,
        "standard_300": 399,
        "bespoke": 0,
    }


def _get_tier_for_client_count(cnt: int) -> str:
    """Derive plan tier from active client count using DB tiers or defaults."""
    tiers = PricingTier.query.filter_by(active=True).order_by(
        PricingTier.sort_order.asc()
    ).all()
    if tiers:
        for t in reversed(tiers):
            if t.client_limit is None or cnt <= t.client_limit:
                result = t.tier_key
        return result if tiers else "free_starter"
    # Fallback
    if cnt <= 5:
        return "free_starter"
    if cnt <= 25:
        return "standard_25"
    if cnt <= 75:
        return "standard_75"
    if cnt <= 150:
        return "standard_150"
    if cnt <= 300:
        return "standard_300"
    return "bespoke"


def _get_report_engine():
    from sqlalchemy import create_engine, text
    db_url = os.getenv(
        "REPORT_DATABASE_URL",
        "postgresql+psycopg://hapireport:dev-only-local-password@127.0.0.1:5432/hapireport"
    )
    db_path = os.getenv(
        "REPORT_DB_PATH",
        "/var/home/hapi/nostromo_ai/projects/hapitech.report/instance/dev.db"
    )
    pg_error = None
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:
        pg_error = exc

    # Try fallback URL driver format if psycopg fails or psycopg2 is present
    if "postgresql+psycopg://" in db_url:
        try:
            alt_url = db_url.replace("postgresql+psycopg://", "postgresql://")
            engine = create_engine(alt_url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception:
            pass

    # Only attempt SQLite fallback if the target file actually exists on disk
    if os.path.isfile(db_path):
        sqlite_url = f"sqlite:///{db_path}"
        return create_engine(sqlite_url)

    raise RuntimeError(f"PostgreSQL connection failed ({pg_error}) and no SQLite fallback database file exists at {db_path}")


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
            # Check which columns exist for graceful degradation
            cols = set()
            try:
                col_rows = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'companies'"
                )).scalars().all()
                cols = set(col_rows)
            except Exception:
                pass

            select_cols = "c.id, c.name, c.slug, c.email, c.created_at"
            if "plan_override" in cols:
                select_cols += ", c.plan_override"
            if "primary_color" in cols:
                select_cols += ", c.primary_color"
            if "secondary_color" in cols:
                select_cols += ", c.secondary_color"

            rows = conn.execute(text(f"""
                SELECT {select_cols}
                FROM companies c
                ORDER BY c.id
            """)).mappings().all()
            companies = [dict(r) for r in rows]

            PLAN_TIERS, MONTHLY_FEES = _get_plan_tiers()

            for co in companies:
                cnt = conn.execute(text(
                    "SELECT COUNT(*) FROM clients WHERE company_id = :cid AND active = true"
                ), {"cid": co["id"]}).scalar() or 0
                co["active_client_count"] = cnt

                # Use override if set, else derive from client count
                override = co.pop("plan_override", None)
                if override and override in PLAN_TIERS:
                    co["plan_tier"] = override
                else:
                    co["plan_tier"] = _get_tier_for_client_count(cnt)
                co["plan_tier_label"] = PLAN_TIERS.get(co["plan_tier"], co["plan_tier"])
                co["monthly_fee"] = MONTHLY_FEES.get(co["plan_tier"], 0)

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
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    # Build dot-calendar data for each tenant
    _, monthly_fees = _get_plan_tiers()
    for t in tenants:
        tier = t.get("plan_tier", "free_starter")
        monthly_fee = monthly_fees.get(tier, 0)

        if tier == "free_starter":
            t["dots"] = []  # Free tenants don't need payment dots
            t["current_month_status"] = "FREE"
        else:
            # Get last 6 months of payment status
            dots = []
            for i in range(5, -1, -1):
                # Calculate month offset
                month_date = now.replace(day=1)
                month_date = month_date - __import__('datetime').timedelta(days=32 * i)
                m = month_date.strftime("%Y-%m")

                status_record = MonthlyPaymentStatus.query.filter_by(
                    entity_type="report_tenant",
                    entity_id=t["id"],
                    month=m
                ).first()

                if status_record:
                    dots.append({"month": m, "status": status_record.status})
                else:
                    # Default: DUE for past months, DUE for current
                    dots.append({"month": m, "status": "DUE"})

            t["dots"] = dots

            # Current month status
            current_record = MonthlyPaymentStatus.query.filter_by(
                entity_type="report_tenant",
                entity_id=t["id"],
                month=current_month
            ).first()
            t["current_month_status"] = current_record.status if current_record else "DUE"
            t["monthly_fee"] = monthly_fee

    return render_template(
        "admin/report_tenants/index.html",
        tenants=tenants,
        db_error=db_error,
        current_month=current_month,
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
    Mark a tenant's current month as PAID in the dot-calendar system.
    Creates or updates the MonthlyPaymentStatus record.
    """
    from sqlalchemy import text
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    engine = _get_report_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, name FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).mappings().first()
        if not row:
            flash(f"Tenant #{tenant_id} not found.", "error")
            return redirect(url_for("report_tenants.report_tenants"))

        # Get tenant's plan tier and fee
        cnt = conn.execute(text(
            "SELECT COUNT(*) FROM clients WHERE company_id = :cid AND active = true"
        ), {"cid": tenant_id}).scalar() or 0

        # Check plan_override
        PLAN_TIERS, MONTHLY_FEES = _get_plan_tiers()
        override = conn.execute(text(
            "SELECT plan_override FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).scalar()
        tier = override if override in PLAN_TIERS else _get_tier_for_client_count(cnt)
        monthly_fee = MONTHLY_FEES.get(tier, 0)

    # Update or create monthly payment status
    existing = MonthlyPaymentStatus.query.filter_by(
        entity_type="report_tenant",
        entity_id=tenant_id,
        month=current_month
    ).first()

    if existing:
        existing.status = "PAID"
        existing.amount_gbp = monthly_fee
        existing.marked_paid_at = now
    else:
        record = MonthlyPaymentStatus(
            entity_type="report_tenant",
            entity_id=tenant_id,
            month=current_month,
            status="PAID",
            amount_gbp=monthly_fee,
            marked_paid_at=now,
        )
        db.session.add(record)

    db.session.commit()
    flash(f"Tenant '{row['name']}' marked as PAID for {current_month}.", "success")
    return redirect(url_for("report_tenants.report_tenants"))


@report_tenants_bp.route("/report-tenants/register", methods=["POST"])
@admin_required
def report_tenants_register():
    """
    Onboard a new tenant company + primary admin user onto hapitech.report,
    seed default item categories, and send an onboarding email with credentials.
    """
    from utils.mailer import send_contact_email
    from sqlalchemy import text

    # Argon2id hashing — match hapitech.report/api/models/user.py
    try:
        from argon2 import PasswordHasher as Argon2Hasher
        _pw_hasher = Argon2Hasher()
        def _hash_password(pw: str) -> str:
            return _pw_hasher.hash(pw)
    except ImportError:
        from werkzeug.security import generate_password_hash
        def _hash_password(pw: str) -> str:
            return generate_password_hash(pw)

    name = (request.form.get("name") or "").strip()
    slug = (request.form.get("slug") or "").strip().lower().replace(" ", "-")
    email = (request.form.get("email") or "").strip().lower()

    if not (name and slug and email):
        flash("Name, slug, and admin email are required.", "error")
        return redirect(url_for("report_tenants.report_tenants"))

    temp_password = "HapiTech2026!Onboard"
    pw_hash = _hash_password(temp_password)
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

    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    # Build dot-calendar data for each client
    for c in clients:
        dots = []
        for i in range(5, -1, -1):
            month_date = now.replace(day=1)
            month_date = month_date - __import__('datetime').timedelta(days=32 * i)
            m = month_date.strftime("%Y-%m")

            status_record = MonthlyPaymentStatus.query.filter_by(
                entity_type="webdev_client",
                entity_id=c.id,
                month=m
            ).first()

            if status_record:
                dots.append({"month": m, "status": status_record.status})
            else:
                dots.append({"month": m, "status": "DUE"})

        c.dots = dots
        c.current_month_status = MonthlyPaymentStatus.query.filter_by(
            entity_type="webdev_client",
            entity_id=c.id,
            month=current_month
        ).first()
        if c.current_month_status:
            c.current_month_status = c.current_month_status.status
        else:
            c.current_month_status = "DUE"

    return render_template(
        "admin/report_tenants/webdev_clients.html",
        clients=clients,
        total_jobs=total_jobs,
        total_paid=total_paid,
        current_month=current_month,
    )


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
    recurring_items = RecurringPayment.query.filter_by(
        client_type="webdev", client_id=client_id
    ).order_by(RecurringPayment.next_due_date.asc().nullslast()).all()
    return render_template("admin/report_tenants/webdev_client_detail.html",
                           client=client, recurring_items=recurring_items)


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


# ---------------------------------------------------------------------------
# Webdev Clients — Dot-Calendar Mark as Paid
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/webdev-clients/<int:client_id>/mark-paid", methods=["POST"])
@admin_required
def webdev_client_mark_paid(client_id):
    """
    Mark a webdev client's current month as PAID in the dot-calendar system.
    """
    client = WebdevClient.query.get_or_404(client_id)
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")

    # Calculate amount from client's total or use a default
    amount = float(client.total_paid_gbp or 0)

    existing = MonthlyPaymentStatus.query.filter_by(
        entity_type="webdev_client",
        entity_id=client_id,
        month=current_month
    ).first()

    if existing:
        existing.status = "PAID"
        existing.amount_gbp = amount
        existing.marked_paid_at = now
    else:
        record = MonthlyPaymentStatus(
            entity_type="webdev_client",
            entity_id=client_id,
            month=current_month,
            status="PAID",
            amount_gbp=amount,
            marked_paid_at=now,
        )
        db.session.add(record)

    db.session.commit()
    flash(f"Client '{client.name}' marked as PAID for {current_month}.", "success")
    return redirect(url_for("report_tenants.webdev_clients"))


# ---------------------------------------------------------------------------
# Tenant Management Controls — upgrade, edit, push-upgrade
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/report-tenants/<int:tenant_id>/upgrade", methods=["POST"])
@admin_required
def report_tenants_upgrade(tenant_id):
    """Cycle a tenant's plan tier through available tiers."""
    from sqlalchemy import text
    engine = _get_report_engine()
    PLAN_TIERS, _ = _get_plan_tiers()
    tier_keys = list(PLAN_TIERS.keys())

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, name FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).mappings().first()
        if not row:
            flash(f"Tenant #{tenant_id} not found.", "error")
            return redirect(url_for("report_tenants.report_tenants"))

        # Get current override
        current_override = conn.execute(text(
            "SELECT plan_override FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).scalar()

        # Cycle to the next tier
        if current_override and current_override in tier_keys:
            idx = tier_keys.index(current_override)
            new_tier = tier_keys[(idx + 1) % len(tier_keys)]
        else:
            new_tier = tier_keys[0] if tier_keys else "free_starter"

        try:
            conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS plan_override VARCHAR(30)"
            ))
            conn.execute(text(
                "UPDATE companies SET plan_override = :tier WHERE id = :tid"
            ), {"tier": new_tier, "tid": tenant_id})
            conn.commit()
        except Exception:
            pass

    flash(f"Tenant '{row['name']}' plan set to {PLAN_TIERS.get(new_tier, new_tier)}.", "success")
    return redirect(url_for("report_tenants.report_tenants"))


@report_tenants_bp.route("/report-tenants/<int:tenant_id>/edit", methods=["POST"])
@admin_required
def report_tenants_edit(tenant_id):
    """Update a tenant's company name, admin email, and branding colours."""
    from sqlalchemy import text
    engine = _get_report_engine()

    new_name = (request.form.get("name") or "").strip()
    new_email = (request.form.get("email") or "").strip()
    primary_color = (request.form.get("primary_color") or "#1e3a5f").strip()
    secondary_color = (request.form.get("secondary_color") or "#4db6ff").strip()

    if not new_name:
        flash("Company name is required.", "error")
        return redirect(url_for("report_tenants.report_tenants"))

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT id FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).mappings().first()
        if not row:
            flash(f"Tenant #{tenant_id} not found.", "error")
            return redirect(url_for("report_tenants.report_tenants"))

        conn.execute(text(
            """UPDATE companies
               SET name = :name, email = :email,
                   primary_color = :pc, secondary_color = :sc
               WHERE id = :tid"""
        ), {"name": new_name, "email": new_email, "pc": primary_color,
            "sc": secondary_color, "tid": tenant_id})

    flash(f"Tenant '{new_name}' updated.", "success")
    return redirect(url_for("report_tenants.report_tenants"))


@report_tenants_bp.route("/report-tenants/<int:tenant_id>/push-upgrade", methods=["POST"])
@admin_required
def report_tenants_push_upgrade(tenant_id):
    """Trigger platform update checks / migrations for a tenant."""
    from sqlalchemy import text
    engine = _get_report_engine()
    results = []

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, name FROM companies WHERE id = :tid"
        ), {"tid": tenant_id}).mappings().first()
        if not row:
            flash(f"Tenant #{tenant_id} not found.", "error")
            return redirect(url_for("report_tenants.report_tenants"))

        company_name = row["name"]

        # 1. Ensure plan_override column exists
        try:
            conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS plan_override VARCHAR(30)"
            ))
            results.append(("Schema check", "OK", "plan_override column ensured"))
        except Exception as e:
            results.append(("Schema check", "WARN", str(e)))

        # 2. Ensure outcome_config column exists
        try:
            conn.execute(text(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS outcome_config JSONB"
            ))
            results.append(("Outcome config", "OK", "outcome_config column ensured"))
        except Exception as e:
            results.append(("Outcome config", "WARN", str(e)))

        # 3. Ensure is_reattempt column on jobs
        try:
            conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_reattempt BOOLEAN DEFAULT false"
            ))
            conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reattempt_count INTEGER DEFAULT 0"
            ))
            conn.execute(text(
                "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS reattempt_reason TEXT"
            ))
            results.append(("Job reattempt fields", "OK", "Columns ensured"))
        except Exception as e:
            results.append(("Job reattempt fields", "WARN", str(e)))

        # 4. Ensure default item categories exist
        try:
            cat_count = conn.execute(text(
                "SELECT COUNT(*) FROM item_categories WHERE company_id = :cid"
            ), {"cid": tenant_id}).scalar() or 0
            if cat_count == 0:
                default_categories = [
                    ("Lifting Equipment & Tackle", '["LOLER"]', 6),
                    ("Workplace Machinery & Tools", '["PUWER"]', 12),
                    ("Pressure Systems & Vessels", '["PSSR"]', 12),
                ]
                now_dt = datetime.utcnow()
                for cat_name, types_json, interval in default_categories:
                    conn.execute(text(
                        """INSERT INTO item_categories
                           (company_id, name, inspection_types,
                            default_inspection_frequency_months, active, created_at)
                           VALUES (:cid, :name, :types, :interval, true, :now)"""
                    ), {"cid": tenant_id, "name": cat_name, "types": types_json,
                        "interval": interval, "now": now_dt})
                results.append(("Default categories", "OK", f"Seeded {len(default_categories)} categories"))
            else:
                results.append(("Default categories", "OK", f"{cat_count} categories already present"))
        except Exception as e:
            results.append(("Default categories", "WARN", str(e)))

    summary = "; ".join(f"{c}: {s}" for c, s, _ in results)
    flash(f"Push-upgrade complete for '{company_name}': {summary}", "success")
    return redirect(url_for("report_tenants.report_tenants"))


# ---------------------------------------------------------------------------
# Recurring Payments — shared helpers
# ---------------------------------------------------------------------------

def _get_recurring_payments(client_type=None, client_id=None):
    q = RecurringPayment.query
    if client_type:
        q = q.filter_by(client_type=client_type)
    if client_id is not None:
        q = q.filter_by(client_id=client_id)
    return q.order_by(RecurringPayment.next_due_date.asc().nullslast()).all()


# ---------------------------------------------------------------------------
# Recurring Payments — Report Tenants
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/report-tenants/<int:tenant_id>/recurring/new", methods=["POST"])
@admin_required
def report_tenant_recurring_new(tenant_id):
    title = (request.form.get("title") or "").strip()
    amount = request.form.get("amount_gbp", "0")
    interval = request.form.get("billing_interval", "monthly")
    due_str = request.form.get("next_due_date", "")

    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("report_tenants.report_tenants"))

    from datetime import date
    due_date = None
    if due_str:
        try:
            due_date = date.fromisoformat(due_str)
        except ValueError:
            pass

    rp = RecurringPayment(
        client_type="report_tenant",
        client_id=tenant_id,
        title=title,
        amount_gbp=float(amount or 0),
        billing_interval=interval,
        next_due_date=due_date,
        payment_status="UNPAID",
        status="active",
    )
    db.session.add(rp)
    db.session.commit()
    flash(f"Recurring item '{title}' added for tenant #{tenant_id}.", "success")
    return redirect(url_for("report_tenants.report_tenants"))


@report_tenants_bp.route("/recurring/<int:rp_id>/toggle-paid", methods=["POST"])
@admin_required
def recurring_toggle_paid(rp_id):
    rp = RecurringPayment.query.get_or_404(rp_id)
    rp.payment_status = "PAID" if rp.payment_status != "PAID" else "UNPAID"
    db.session.commit()
    flash(f"Payment status for '{rp.title}' set to {rp.payment_status}.", "success")
    # Redirect back to the originating page
    if rp.client_type == "report_tenant":
        return redirect(url_for("report_tenants.report_tenants"))
    return redirect(url_for("report_tenants.webdev_client_view", client_id=rp.client_id))


@report_tenants_bp.route("/recurring/<int:rp_id>/cancel", methods=["POST"])
@admin_required
def recurring_cancel(rp_id):
    rp = RecurringPayment.query.get_or_404(rp_id)
    rp.status = "cancelled"
    db.session.commit()
    flash(f"Recurring item '{rp.title}' cancelled.", "success")
    if rp.client_type == "report_tenant":
        return redirect(url_for("report_tenants.report_tenants"))
    return redirect(url_for("report_tenants.webdev_client_view", client_id=rp.client_id))


# ---------------------------------------------------------------------------
# Recurring Payments — Webdev Clients
# ---------------------------------------------------------------------------

@report_tenants_bp.route("/webdev-clients/<int:client_id>/recurring/new", methods=["POST"])
@admin_required
def webdev_recurring_new(client_id):
    title = (request.form.get("title") or "").strip()
    amount = request.form.get("amount_gbp", "0")
    interval = request.form.get("billing_interval", "monthly")
    due_str = request.form.get("next_due_date", "")

    if not title:
        flash("Title is required.", "error")
        return redirect(url_for("report_tenants.webdev_client_view", client_id=client_id))

    from datetime import date
    due_date = None
    if due_str:
        try:
            due_date = date.fromisoformat(due_str)
        except ValueError:
            pass

    rp = RecurringPayment(
        client_type="webdev",
        client_id=client_id,
        title=title,
        amount_gbp=float(amount or 0),
        billing_interval=interval,
        next_due_date=due_date,
        payment_status="UNPAID",
        status="active",
    )
    db.session.add(rp)
    db.session.commit()
    flash(f"Recurring item '{title}' added for client #{client_id}.", "success")
    return redirect(url_for("report_tenants.webdev_client_view", client_id=client_id))
