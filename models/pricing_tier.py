"""
PricingTier — configurable subscription tiers for hapitech.report tenants.

Each tier defines a client-company limit and a monthly price in GBP.
Tier definitions are managed from the hapitech.dev admin portal and
stored in the database so they can be edited without code changes.
"""
import datetime
from . import db


class PricingTier(db.Model):
    __tablename__ = "pricing_tiers"

    id = db.Column(db.Integer, primary_key=True)

    # Stable key used in plan_override values on hapitech.report companies
    tier_key = db.Column(db.String(30), unique=True, nullable=False, index=True)

    # Human-readable label displayed in the admin UI
    name = db.Column(db.String(80), nullable=False)

    # Maximum client companies this tier allows (None = unlimited / bespoke)
    client_limit = db.Column(db.Integer, nullable=True)

    # Monthly subscription fee in GBP
    monthly_price_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # Display order in the admin UI
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    # Whether this is a legacy tier or current
    active = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow, nullable=False)

    @classmethod
    def seed_defaults(cls):
        """Seed the 6 standard pricing tiers into the database if empty."""
        defaults = [
            ("free_starter", "Free Starter", 5, 0.0, 10),
            ("standard_25", "Standard — 25 Clients", 25, 79.0, 20),
            ("standard_75", "Standard — 75 Clients", 75, 149.0, 30),
            ("standard_150", "Standard — 150 Clients", 150, 249.0, 40),
            ("standard_300", "Standard — 300 Clients", 300, 399.0, 50),
            ("bespoke", "Bespoke (300+ Clients)", None, 0.0, 60),
        ]
        seeded = 0
        for tier_key, name, limit, price, sort in defaults:
            existing = cls.query.filter_by(tier_key=tier_key).first()
            if not existing:
                tier = cls(
                    tier_key=tier_key,
                    name=name,
                    client_limit=limit,
                    monthly_price_gbp=price,
                    sort_order=sort,
                    active=True,
                )
                db.session.add(tier)
                seeded += 1
        if seeded > 0:
            db.session.commit()
        return seeded

    def __repr__(self):
        return f"<PricingTier {self.tier_key} £{self.monthly_price_gbp}/{self.client_limit}>"
