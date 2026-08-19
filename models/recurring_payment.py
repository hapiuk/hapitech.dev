"""
RecurringPayment — tracks recurring subscription items for webdev clients
and hapitech.report inspection tenants.

Each record represents one billing line (e.g. "Monthly Hosting", "Growth Plan"),
with amount, interval, next due date, and payment lifecycle status.
"""
import datetime
from . import db


class RecurringPayment(db.Model):
    __tablename__ = "recurring_payments"

    id = db.Column(db.Integer, primary_key=True)

    # Polymorphic owner — exactly one of these is set
    client_type = db.Column(db.String(20), nullable=False)   # "webdev" | "report_tenant"
    client_id = db.Column(db.Integer, nullable=False)          # webdev_clients.id or company id from report DB

    title = db.Column(db.String(200), nullable=False)
    amount_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    billing_interval = db.Column(db.String(20), nullable=False, default="monthly")
    # monthly | quarterly | annually | one-off

    next_due_date = db.Column(db.Date, nullable=True)

    payment_status = db.Column(db.String(10), nullable=False, default="UNPAID")
    # PAID | UNPAID | OVERDUE

    status = db.Column(db.String(20), nullable=False, default="active")
    # active | cancelled

    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow,
                           onupdate=datetime.datetime.utcnow, nullable=False)

    # Convenience -----------------------------------------------------------------

    @property
    def owner_label(self):
        return "Report Tenant" if self.client_type == "report_tenant" else "Webdev Client"

    def __repr__(self):
        return f"<RecurringPayment {self.id} {self.title} £{self.amount_gbp}/{self.billing_interval}>"
