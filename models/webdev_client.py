"""
WebdevClient — tracks web-development agency clients (e.g. Roland's Handyman,
Ray G's Handyman).  Entirely separate from hapitech.report inspection tenants.
"""
import datetime
from . import db


class WebdevClient(db.Model):
    __tablename__ = "webdev_clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    domain = db.Column(db.String(200), nullable=True)
    contact_name = db.Column(db.String(120), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)  # active/paused/archived

    # financial summary
    payment_status = db.Column(db.String(10), default="UNPAID", nullable=False)  # PAID/UNPAID
    total_paid_gbp = db.Column(db.Numeric(10, 2), default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow, nullable=False)

    jobs = db.relationship("WebdevJob", backref="client", lazy=True,
                           cascade="all, delete-orphan",
                           order_by="WebdevJob.created_at.desc()")


class WebdevJob(db.Model):
    """A priced task / job for a webdev client (website build, SEO audit, etc.)"""
    __tablename__ = "webdev_jobs"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("webdev_clients.id"), nullable=False)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    job_type = db.Column(db.String(60), default="other", nullable=False)
    # website_build / seo_audit / maintenance / design / hosting / other

    price_gbp = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    payment_status = db.Column(db.String(10), default="UNPAID", nullable=False)  # PAID/UNPAID

    status = db.Column(db.String(20), default="pending", nullable=False)
    # pending / in_progress / completed / cancelled

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow, nullable=False)
