"""
MonthlyPaymentStatus — dot-calendar payment tracking for report tenants
and webdev clients. Each record tracks one month's payment status for
a specific entity (tenant or client).
"""
import datetime
from . import db


class MonthlyPaymentStatus(db.Model):
    __tablename__ = "monthly_payment_status"

    id = db.Column(db.Integer, primary_key=True)

    # Polymorphic owner
    entity_type = db.Column(db.String(20), nullable=False)  # "report_tenant" | "webdev_client"
    entity_id = db.Column(db.Integer, nullable=False)        # company_id or webdev_clients.id

    month = db.Column(db.String(7), nullable=False)          # "YYYY-MM"
    status = db.Column(db.String(10), nullable=False, default="DUE")
    # PAID | DUE | OVERDUE | FREE

    amount_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    marked_paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("entity_type", "entity_id", "month",
                            name="uq_entity_month"),
    )

    def __repr__(self):
        return f"<MonthlyPaymentStatus {self.entity_type}:{self.entity_id} {self.month} {self.status}>"
