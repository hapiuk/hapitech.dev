# models/core.py — accounts (businesses), users, and the money side: jobs, subscriptions, payments.
import datetime as dt
import re

from flask_login import UserMixin

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
    google_profile_url = db.Column(db.String(500))                           # Google "write a review" link
    balance_gbp = db.Column(db.Numeric(10, 2))                               # what they owe HapiTech (shown on Finances)
    billing_note = db.Column(db.Text)                                        # optional message on their Finances page
    google_reviews_url = db.Column(db.String(500))
    google_rating = db.Column(db.Numeric(2, 1))                              # headline numbers from the last import
    google_count = db.Column(db.Integer)
    google_maps_url = db.Column(db.String(600))                              # where to run the Google export
    facebook_url = db.Column(db.String(300))
    facebook_pct = db.Column(db.Integer)                                     # "% recommend" on Facebook
    facebook_count = db.Column(db.Integer)
    reviews_synced_at = db.Column(db.DateTime)
    shortcuts = db.Column(db.Text)                                           # JSON [[label, url], …] on their Jobs page
    features = db.Column(db.Text)                                            # JSON ["reviews", …]; blank = everything
    languages = db.Column(db.String(40))                                     # extra dashboard languages, e.g. "lv"

    @property
    def offers_lv(self):
        return "lv" in (self.languages or "").split(",")

    @property
    def feature_set(self):
        """Dashboard sections they get: reviews, website, jobs. Blank = all (everyone set up before this existed)."""
        import json as _json
        from utils.features import ALL
        try:
            got = [f for f in _json.loads(self.features or "null") or ALL if f in ALL]
        except (ValueError, TypeError):
            got = list(ALL)
        return set(got or ALL)

    def has_feature(self, name):
        return name in self.feature_set

    @property
    def shortcut_list(self):
        import json as _json
        try:
            return [(l, u) for l, u in _json.loads(self.shortcuts or "[]") if str(u).startswith("https://")]
        except (ValueError, TypeError):
            return []                           # page listing their Google reviews ("via Google")
    logo_path = db.Column(db.String(300))                                    # static-relative path
    brand_colour = db.Column(db.String(9))                                   # "#f97316"
    notes = db.Column(db.Text)
    site_api_key_hash = db.Column(db.String(255))                            # client-site read key (hashed)
    # quotes & invoices (shown on the customer's copy)
    business_address = db.Column(db.Text)
    vat_number = db.Column(db.String(40))                                    # blank = not VAT registered
    payment_details = db.Column(db.Text)                                     # e.g. bank name / sort code / account
    pay_link_kind = db.Column(db.String(20))                                 # revolut | paypal | monzo | sumup | stripe | other
    pay_link = db.Column(db.String(300))                                     # their link; one "Pay now" button on invoices
    pay_bank = db.Column(db.Boolean, nullable=False, default=False)          # show bank transfer details on invoices
    bank_name = db.Column(db.String(80))
    bank_account_name = db.Column(db.String(120))
    bank_sort_code = db.Column(db.String(8))                                 # "00-00-00"
    bank_account_number = db.Column(db.String(8))
    pay_note = db.Column(db.Text)                                            # message on invoices; blank = the default

    DEFAULT_PAY_NOTE = "Thanks! Use the payment link provided, or quote your reference in your bank transfer."

    @property
    def bank_rows(self):
        """Bank transfer details as (label, value) rows; falls back to the old free-text details."""
        rows = [(k, v) for k, v in (("Bank", self.bank_name), ("Account name", self.bank_account_name),
                                    ("Sort code", self.bank_sort_code), ("Account number", self.bank_account_number)) if v]
        if not rows and (self.payment_details or "").strip():
            rows = [("Details", self.payment_details.strip())]
        return rows

    @property
    def has_bank(self):
        return bool(self.bank_sort_code and self.bank_account_number) or bool((self.payment_details or "").strip())

    @property
    def pay_message(self):
        return (self.pay_note or "").strip() or self.DEFAULT_PAY_NOTE
    quote_terms = db.Column(db.Text)
    # holiday / away mode (shown on their website while active)
    away_until = db.Column(db.Date)
    away_message = db.Column(db.String(200))
    # secret for the phone-calendar feed (.ics); regenerate to revoke
    calendar_token = db.Column(db.String(48))

    @property
    def is_away(self):
        import datetime as _dt
        return bool(self.away_until and self.away_until >= _dt.date.today())

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
    password_hash = db.Column(db.String(255), nullable=False, default="")   # unused: login is by email code only
    role = db.Column(db.String(20), nullable=False, default="owner")         # admin | owner | staff
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    client_id = db.Column(db.Integer, nullable=True)                         # legacy column, unused
    is_active_flag = db.Column("is_active", db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime)                                  # last time they typed in a login code
    last_seen_at = db.Column(db.DateTime)                                   # last time they used it (updated ≤ every 10 min)
    prefs = db.Column(db.Text)                                              # JSON: small personal settings

    def pref(self, key, default=None):
        import json as _json
        try:
            return (_json.loads(self.prefs or "{}") or {}).get(key, default)
        except (ValueError, TypeError):
            return default

    def set_pref(self, key, value):
        import json as _json
        try:
            d = _json.loads(self.prefs or "{}") or {}
        except (ValueError, TypeError):
            d = {}
        d[key] = value
        self.prefs = _json.dumps(d)

    account = db.relationship("Account", back_populates="users")

    @property
    def is_active(self):            # Flask-Login: disabled users can't log in
        return bool(self.is_active_flag)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_owner(self):
        """Owners (and admins viewing a client) can manage money, website and staff; staff can't."""
        return self.role in ("owner", "admin")

    @property
    def home_url(self):
        return "/admin" if self.is_admin else "/portal"



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
    status = db.Column(db.String(20), nullable=False, default="trial")       # trial | friends | active | paused
    trial_ends_at = db.Column(db.Date)                                         # trial / friends plan end date
    renew_months = db.Column(db.Integer)                                       # friends plan: auto-renew period (None = off)
    account = db.relationship("Account", back_populates="addons")

    @property
    def is_enabled(self):
        if self.status == "active":
            return True
        if self.status == "friends" and self.renew_months:
            return True                                    # auto-renewing: never lapses (the date rolls forward)
        if self.status in ("trial", "friends"):
            return self.trial_ends_at is None or self.trial_ends_at >= dt.date.today()
        return False

    @property
    def plan(self):
        from utils.plans import describe
        return describe(self)

    @property
    def trial_days_left(self):
        if self.status not in ("trial", "friends") or not self.trial_ends_at:
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

    @property
    def ref(self):
        return f"R-{self.id}"

    @property
    def status_label(self):
        return {"new": "Received", "doing": "Accepted", "done": "Done"}.get(self.status, self.status)

    @property
    def task(self):
        from .tasks import Task
        return Task.query.filter_by(change_request_id=self.id).first()


class LoginAttempt(db.Model):
    """Failed/successful logins, used for rate limiting across workers."""
    __tablename__ = "login_attempts"
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), index=True)
    email = db.Column(db.String(255), index=True)
    kind = db.Column(db.String(20), nullable=False, default="password")      # password | code
    success = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)


class RunningCost(db.Model):
    """Ongoing costs of running a client's site (hosting, email, domain). `value_gbp` is what it would cost
    THEM to buy it themselves (shown on their My plan page); `my_cost_gbp` is what it costs HapiTech
    (admin only, for pricing). `covered` = HapiTech pays it for them at the moment."""
    __tablename__ = "running_costs"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="other")       # hosting | email | domain | other
    value_gbp = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    my_cost_gbp = db.Column(db.Numeric(10, 2))
    interval = db.Column(db.String(10), nullable=False, default="monthly")  # monthly | quarterly | yearly | once
    started_on = db.Column(db.Date)
    ended_on = db.Column(db.Date)
    covered = db.Column(db.Boolean, nullable=False, default=True)
    note = db.Column(db.String(300))
    account = db.relationship("Account", backref=db.backref("running_costs", lazy=True, order_by="RunningCost.id"))

    STEP_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}

    @property
    def monthly(self):
        """Monthly equivalent of the price (one-off items: 0)."""
        v = float(self.value_gbp or 0)
        return v / self.STEP_MONTHS[self.interval] if self.interval in self.STEP_MONTHS else 0.0

    @property
    def my_monthly(self):
        if self.my_cost_gbp is None:
            return None
        v = float(self.my_cost_gbp)
        return v / self.STEP_MONTHS[self.interval] if self.interval in self.STEP_MONTHS else 0.0

    def charge_dates(self, until):
        """Every date this is charged, from started_on up to `until` (one-offs: just the start date)."""
        from utils.plans import add_months
        if not self.started_on:
            return []
        end = min(self.ended_on, until) if self.ended_on else until
        if self.interval not in self.STEP_MONTHS:
            return [self.started_on] if self.started_on <= end else []
        out, k = [], 0
        while True:
            d = add_months(self.started_on, k * self.STEP_MONTHS[self.interval])
            if d > end:
                return out
            out.append(d)
            k += 1

    def value_so_far(self, today=None):
        today = today or dt.date.today()
        return round(float(self.value_gbp or 0) * len(self.charge_dates(today)), 2)

    def months_active(self, today=None):
        today = today or dt.date.today()
        if not self.started_on or self.started_on > today:
            return 0.0
        end = min(self.ended_on or today, today)
        return max(0.0, (end - self.started_on).days / (365.25 / 12))


class SystemState(db.Model):
    """Small key/value store: scheduler lease, last-run times."""
    __tablename__ = "system_state"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
