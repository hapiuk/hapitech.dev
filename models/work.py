# models/work.py — the client's own work: enquiries -> quotes -> bookings -> done -> invoices.
# One Lead row is one customer job from first contact to finish, so contact details live in
# one place and can be deleted in one go.
#
# Retention (Aaron, 22 Nov 2026):
#   - accepted / booked / done jobs are never deleted automatically: archive, then delete from archive
#   - jobs that were never accepted (new, quoted, declined) can be deleted any time
#   - declined jobs are deleted automatically 30 days after being declined
import datetime as dt
import json
import secrets

from . import db
from .core import TimestampMixin, utcnow

LEAD_STATUSES = [("new", "New enquiry"), ("quoted", "Quote sent"), ("accepted", "Accepted, needs a date"),
                 ("booked", "Booked"), ("done", "Done"), ("declined", "Not going ahead")]
ACCEPTED = ("accepted", "booked", "done")
DECLINED_RETENTION_DAYS = 30


def _token():
    return secrets.token_urlsafe(18)


class Lead(TimestampMixin, db.Model):
    __tablename__ = "leads"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, default="manual")   # website | booking | manual | phone
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    # customer
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(40))
    postcode = db.Column(db.String(12))
    address = db.Column(db.Text)
    # the job
    title = db.Column(db.String(160))
    message = db.Column(db.Text)
    preferred = db.Column(db.String(200))            # customer's preferred day/time (booking requests)
    travel_note = db.Column(db.String(200))
    notes = db.Column(db.Text)                       # private
    # booking
    start_at = db.Column(db.DateTime, index=True)
    days = db.Column(db.Integer, nullable=False, default=1)
    confirm_sent_at = db.Column(db.DateTime)
    reminder_sent_at = db.Column(db.DateTime)
    review_requested_at = db.Column(db.DateTime)
    done_at = db.Column(db.DateTime)
    declined_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    # HapiTech's own jobs: which client a work request / issue is for, and what they offered (blank = quote me)
    for_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)
    offer_gbp = db.Column(db.Numeric(10, 2))
    account = db.relationship("Account", foreign_keys=[account_id])
    for_account = db.relationship("Account", foreign_keys=[for_account_id])
    quotes = db.relationship("Quote", back_populates="lead", cascade="all, delete-orphan",
                             order_by="Quote.created_at.desc()")
    invoices = db.relationship("Invoice", back_populates="lead", cascade="all, delete-orphan",
                               order_by="Invoice.created_at.desc()")
    repeat_reminders = db.relationship("RepeatReminder", back_populates="lead", cascade="all, delete-orphan")

    @property
    def accepted(self):
        return self.status in ACCEPTED

    @property
    def can_delete(self):
        """Never-accepted jobs any time; accepted/done ones only once archived."""
        return (not self.accepted) or self.archived_at is not None

    @property
    def end_at(self):
        return self.start_at + dt.timedelta(days=max(1, self.days) - 1) if self.start_at else None

    @property
    def label(self):
        return self.title or (self.message or "").split("\n")[0][:60] or "Job"

    @property
    def status_label(self):
        return dict(LEAD_STATUSES).get(self.status, self.status)

    @property
    def delete_on(self):
        if self.status == "declined" and self.declined_at:
            return (self.declined_at + dt.timedelta(days=DECLINED_RETENTION_DAYS)).date()
        return None


def _items_total(items_json, vat_rate):
    try:
        items = json.loads(items_json or "[]")
    except ValueError:
        items = []
    net = sum(float(i.get("qty") or 0) * float(i.get("price") or 0) for i in items)
    vat = round(net * float(vat_rate or 0) / 100, 2)
    return round(net, 2), vat, round(net + vat, 2)


class _Priced:
    @property
    def item_list(self):
        try:
            return json.loads(self.items or "[]")
        except ValueError:
            return []

    @property
    def totals(self):
        return _items_total(self.items, self.vat_rate)


class Quote(_Priced, TimestampMixin, db.Model):
    __tablename__ = "quotes"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    number = db.Column(db.String(20), nullable=False)
    items = db.Column(db.Text, nullable=False, default="[]")   # [{"desc","qty","price"}]
    vat_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    valid_until = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="draft")   # draft | sent | accepted | declined
    token = db.Column(db.String(48), unique=True, nullable=False, default=_token)
    sent_at = db.Column(db.DateTime)
    responded_at = db.Column(db.DateTime)
    lead = db.relationship("Lead", back_populates="quotes")


class Invoice(_Priced, TimestampMixin, db.Model):
    __tablename__ = "invoices"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    number = db.Column(db.String(20), nullable=False)
    items = db.Column(db.Text, nullable=False, default="[]")
    vat_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    notes = db.Column(db.Text)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="draft")   # draft | sent | paid
    token = db.Column(db.String(48), unique=True, nullable=False, default=_token)
    sent_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    lead = db.relationship("Lead", back_populates="invoices")


class RepeatReminder(db.Model):
    """"Remind me next autumn about the gutters" — only with the customer's permission."""
    __tablename__ = "repeat_reminders"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, index=True)
    remind_on = db.Column(db.Date, nullable=False, index=True)
    note = db.Column(db.String(200), nullable=False)
    token = db.Column(db.String(48), unique=True, nullable=False, default=_token)   # unsubscribe link
    sent_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    lead = db.relationship("Lead", back_populates="repeat_reminders")


def next_number(model, account_id, prefix):
    """Q-0001 / INV-0001, per client."""
    n = model.query.filter_by(account_id=account_id).count() + 1
    return f"{prefix}-{n:04d}"
