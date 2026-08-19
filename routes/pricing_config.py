"""
routes/pricing_config.py

Dynamic pricing tier management for hapitech.report tenants.
Stores tier definitions in the hapitech.dev database so prices
and limits can be modified from the admin portal without code changes.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash
)
from flask_login import login_required, current_user
from functools import wraps

from models import db
from models.pricing_tier import PricingTier

pricing_config_bp = Blueprint(
    "pricing_config",
    __name__,
    url_prefix="/admin",
)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if getattr(current_user, "role", None) != "admin":
            from flask import abort
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def get_tier_dict():
    """Return pricing tiers as a dict keyed by tier_key, sorted by sort_order."""
    tiers = PricingTier.query.filter_by(active=True).order_by(
        PricingTier.sort_order.asc()
    ).all()
    return {t.tier_key: t for t in tiers}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pricing_config_bp.route("/pricing-config")
@admin_required
def pricing_config():
    """Display and manage all pricing tiers."""
    tiers = PricingTier.query.order_by(PricingTier.sort_order.asc()).all()
    return render_template("admin/pricing_config/index.html", tiers=tiers)


@pricing_config_bp.route("/pricing-config/new", methods=["GET", "POST"])
@admin_required
def pricing_tier_new():
    """Create a new pricing tier."""
    if request.method == "POST":
        f = request.form
        tier_key = (f.get("tier_key") or "").strip().lower().replace(" ", "_")
        name = (f.get("name") or "").strip()
        client_limit_str = (f.get("client_limit") or "").strip()
        monthly_price_str = (f.get("monthly_price_gbp") or "0").strip()
        sort_order_str = (f.get("sort_order") or "0").strip()

        if not tier_key or not name:
            flash("Tier key and name are required.", "error")
            return render_template("admin/pricing_config/form.html", tier=None, action="new")

        # Check for duplicate key
        existing = PricingTier.query.filter_by(tier_key=tier_key).first()
        if existing:
            flash(f"A tier with key '{tier_key}' already exists.", "error")
            return render_template("admin/pricing_config/form.html", tier=None, action="new")

        client_limit = int(client_limit_str) if client_limit_str.isdigit() else None
        monthly_price = float(monthly_price_str) if monthly_price_str else 0
        sort_order = int(sort_order_str) if sort_order_str.isdigit() else 0

        tier = PricingTier(
            tier_key=tier_key,
            name=name,
            client_limit=client_limit,
            monthly_price_gbp=monthly_price,
            sort_order=sort_order,
            active=True,
        )
        db.session.add(tier)
        db.session.commit()
        flash(f"Pricing tier '{name}' created.", "success")
        return redirect(url_for("pricing_config.pricing_config"))

    return render_template("admin/pricing_config/form.html", tier=None, action="new")


@pricing_config_bp.route("/pricing-config/<int:tier_id>/edit", methods=["GET", "POST"])
@admin_required
def pricing_tier_edit(tier_id):
    """Edit an existing pricing tier."""
    tier = PricingTier.query.get_or_404(tier_id)

    if request.method == "POST":
        f = request.form
        tier.name = (f.get("name") or "").strip() or tier.name
        client_limit_str = (f.get("client_limit") or "").strip()
        tier.client_limit = int(client_limit_str) if client_limit_str.isdigit() else None
        tier.monthly_price_gbp = float((f.get("monthly_price_gbp") or "0").strip())
        tier.sort_order = int((f.get("sort_order") or "0").strip() or 0)
        tier.active = bool(f.get("active", True))
        db.session.commit()
        flash(f"Pricing tier '{tier.name}' updated.", "success")
        return redirect(url_for("pricing_config.pricing_config"))

    return render_template("admin/pricing_config/form.html", tier=tier, action="edit")


@pricing_config_bp.route("/pricing-config/<int:tier_id>/delete", methods=["POST"])
@admin_required
def pricing_tier_delete(tier_id):
    """Soft-delete (deactivate) a pricing tier."""
    tier = PricingTier.query.get_or_404(tier_id)
    tier.active = False
    db.session.commit()
    flash(f"Pricing tier '{tier.name}' deactivated.", "success")
    return redirect(url_for("pricing_config.pricing_config"))


@pricing_config_bp.route("/pricing-config/seed-defaults", methods=["POST"])
@admin_required
def pricing_tier_seed():
    """Seed the standard pricing tiers if the table is empty."""
    existing = PricingTier.query.count()
    if existing > 0:
        flash("Tiers already exist — seed skipped.", "info")
        return redirect(url_for("pricing_config.pricing_config"))

    defaults = [
        ("free_starter", "Free Starter", 5, 0, 0),
        ("standard_25", "Standard 25 Clients", 25, 79, 10),
        ("standard_75", "Standard 75 Clients", 75, 149, 20),
        ("standard_150", "Standard 150 Clients", 150, 249, 30),
        ("standard_300", "Standard 300 Clients", 300, 399, 40),
        ("bespoke", "Bespoke (300+)", None, 0, 50),
    ]

    for tier_key, name, limit, price, order in defaults:
        db.session.add(PricingTier(
            tier_key=tier_key,
            name=name,
            client_limit=limit,
            monthly_price_gbp=price,
            sort_order=order,
            active=True,
        ))

    db.session.commit()
    flash(f"Seeded {len(defaults)} default pricing tiers.", "success")
    return redirect(url_for("pricing_config.pricing_config"))
