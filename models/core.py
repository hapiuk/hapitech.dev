# models/core.py — accounts (businesses), users, and the money side: jobs, subscriptions, payments.
import datetime as dt
import re

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


def utcnow():
    return dt.datetime.utcnow()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().replace("'", "")).strip("-")
    return s or "account"


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Account(TimestampMixin, db.Model):
    """A business we work with (a client) — or HapiTech itself (kind='internal')."""
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, default="client")        # client | internal
    status = db.Column(db.String(20), nullable=False, default="active")      # active | paused | archived
    domain = db.Column(db.String(200))
    trade = db.Column(db.String(120))                                        # e.g. "Handyman & property maintenance"
    town = db.Column(db.String(120))
    contact_name = db.Column(db.String(120))
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(40))
    google_profile_url = db.Column(db.String(500))                           # "via Google" links
    logo_path = db.Column(db.String(300))                                    # static-relative path
    brand_colour = db.Column(db.String(9))                                   # "#f97316"
    notes = db.Column(db.Text)
    site_api_key_hash = db.Column(db.String(255))                            # client-site read key (hashed)

    users = db.relationship("User", back_populates="account", lazy=True)
    jobs = db.relationship("Job", back_populates="account", lazy=True, order_by="Job.created_at.desc()",
                           cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", back_populates="account", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="account", lazy=True, order_by="Payment.paid_at.desc()",
                               cascade="all, delete-orphan")
    notes_log = db.relationship("Note", back_populates="account", lazy=True, order_by="Note.created_at.desc()",
                                cascade="all, delete-orphan")
    addons = db.relationship("AddOn", back_populates="account", lazy=True, cascade="all, delete-orphan")

    def addon(self, kind="reviews_updates"):
        return next((a for a in self.addons if a.kind == kind), None)

    def has_addon(self, kind="reviews_updates") -> bool:
        a = self.addon(kind)
        return bool(a and a.is_enabled)

    @property
    def first_name(self):
        return (self.contact_name or self.name).split()[0]


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)        # legacy; mirrors email
    name = db.Column(db.String(120))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="owner")         # admin | owner | staff
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    client_id = db.Column(db.Integer, nullable=True)                         # legacy column, unused
    is_active_flag = db.Column("is_active", db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)

    account = db.relationship("Account", back_populates="users")

    @property
    def is_active(self):            # Flask-Login: disabled users can't log in
        return bool(self.is_active_flag)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def home_url(self):
        return "/admin" if self.is_admin else "/portal"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)


JOB_TYPES = [("build", "Website build"), ("change", "Website change"), ("hosting", "Hosting"),
             ("ai_setup", "Local AI setup"), ("ai_workflow", "AI workflow"), ("ai_intro", "AI introduction"),
             ("it_support", "IT support"), ("other", "Other")]
JOB_STATUSES = [("quote", "Quote"), ("booked", "Booked"), ("in_progress", "In progress"),
                ("done", "Done"), ("cancelled", "Cancelled")]


class Job(TimestampMixin, db.Model):
    __tablename__ = "jobs"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(30), nullable=False, default="other")
    status = db.Column(db.String(20), nullable=False, default="quote")
    price_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    due_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    account = db.relationship("Account", back_populates="jobs")
    payments = db.relationship("Payment", back_populates="job", lazy=True)

    @property
    def paid_gbp(self):
        return sum((p.amount_gbp or 0) for p in self.payments)

    @property
    def is_paid(self):
        return float(self.price_gbp or 0) > 0 and float(self.paid_gbp) >= float(self.price_gbp)


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    amount_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    interval = db.Column(db.String(10), nullable=False, default="monthly")   # monthly | yearly
    next_due = db.Column(db.Date)
    status = db.Column(db.String(20), nullable=False, default="active")      # active | paused | cancelled
    account = db.relationship("Account", back_populates="subscriptions")
    payments = db.relationship("Payment", back_populates="subscription", lazy=True)

    @property
    def monthly_gbp(self):
        a = float(self.amount_gbp or 0)
        return a / 12 if self.interval == "yearly" else a

    def advance(self):
        """Move next_due on by one interval (called when a payment is recorded)."""
        if not self.next_due:
            return
        y, m = self.next_due.year, self.next_due.month + (12 if self.interval == "yearly" else 1)
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        day = min(self.next_due.day, 28)
        self.next_due = dt.date(y, m, day)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"))
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"))
    amount_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    paid_at = db.Column(db.Date, nullable=False, default=lambda: dt.date.today())
    method = db.Column(db.String(30))                                        # bank | cash | card | other
    ref = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    account = db.relationship("Account", back_populates="payments")
    job = db.relationship("Job", back_populates="payments")
    subscription = db.relationship("Subscription", back_populates="payments")


class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    account = db.relationship("Account", back_populates="notes_log")
    author = db.relationship("User")


class AddOn(TimestampMixin, db.Model):
    """Paid extras per account. kind='reviews_updates' = portal + reviews + posts + content edits."""
    __tablename__ = "addons"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False, default="reviews_updates")
    status = db.Column(db.String(20), nullable=False, default="trial")       # trial | active | paused
    trial_ends_at = db.Column(db.Date)
    account = db.relationship("Account", back_populates="addons")

    @property
    def is_enabled(self):
        if self.status == "active":
            return True
        if self.status == "trial":
            return self.trial_ends_at is None or self.trial_ends_at >= dt.date.today()
        return False

    @property
    def trial_days_left(self):
        if self.status != "trial" or not self.trial_ends_at:
            return None
        return max(0, (self.trial_ends_at - dt.date.today()).days)


class ChangeRequest(db.Model):
    __tablename__ = "change_requests"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="new")         # new | doing | done
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    account = db.relationship("Account")
    author = db.relationship("User")


class LoginAttempt(db.Model):
    """Failed/successful logins, used for rate limiting across workers."""
    __tablename__ = "login_attempts"
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), index=True)
    email = db.Column(db.String(255), index=True)
    kind = db.Column(db.String(20), nullable=False, default="password")      # password | code
    success = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
