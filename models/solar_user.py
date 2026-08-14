import secrets
from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db

# Everything in this file lives on its own database file (see SQLALCHEMY_BINDS
# in app.py — bind key "solar"). Nothing here has a foreign key into the
# HapiTech client/user tables, and nothing there references this file.
# That's deliberate: this whole feature should be liftable into its own
# app later by just taking the "solar" database file with it.

CODE_LENGTH = 6
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5


class SolarUser(UserMixin, db.Model):
    __bind_key__ = "solar"
    __tablename__ = "solar_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    is_early_supporter = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    exploration_points = db.Column(db.Integer, nullable=False, default=0)
    scanned_bodies = db.Column(db.Text, nullable=False, default="[]")  # JSON-encoded list of body names

    # No password field — accounts are accessed via emailed one-time codes only.

    def get_id(self):
        # Prefixed so app.py's user_loader can tell this apart from a
        # client-portal User id sharing the same integer space.
        return f"solar-{self.id}"


class SolarLoginCode(db.Model):
    __bind_key__ = "solar"
    __tablename__ = "solar_login_codes"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)

    # Only used when the code is for a not-yet-created account (registration).
    pending_display_name = db.Column(db.String(80), nullable=True)

    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @staticmethod
    def generate_code() -> str:
        # secrets, not random — this is a security token even though it's short-lived.
        return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))

    def set_code(self, raw_code: str) -> None:
        self.code_hash = generate_password_hash(raw_code)
        self.expires_at = datetime.utcnow() + timedelta(minutes=CODE_TTL_MINUTES)

    def check_code(self, raw_code: str) -> bool:
        return check_password_hash(self.code_hash, raw_code)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def is_locked_out(self) -> bool:
        return self.attempts >= MAX_ATTEMPTS


class SolarJournalEntry(db.Model):
    __bind_key__ = "solar"
    __tablename__ = "solar_journal_entries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("solar_users.id"), nullable=False, index=True)

    title = db.Column(db.String(140), nullable=False)
    body = db.Column(db.Text, nullable=True)

    # Which celestial body this entry is about — "general" if not tied to one.
    entity_kind = db.Column(db.String(20), nullable=False, default="general")
    entity_name = db.Column(db.String(80), nullable=False, default="General", index=True)

    # Private by default — the poster opts in to sharing with the community.
    is_public = db.Column(db.Boolean, nullable=False, default=False)

    image_filename = db.Column(db.String(255), nullable=True)
    # Stored so the global storage ceiling can be checked with SUM() instead
    # of walking the filesystem on every upload.
    image_size_bytes = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("SolarUser", backref=db.backref("journal_entries", lazy=True))