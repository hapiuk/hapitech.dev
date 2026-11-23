# models/reviews.py — the HapiTech review system. hapitech.dev is the system of record;
# client sites read published reviews through the site API.
import secrets

from . import db
from .core import TimestampMixin, utcnow

REVIEW_SOURCES = {"hapitech": "HapiTech", "website": "their website", "google": "Google", "facebook": "Facebook",
                  "checkatrade": "Checkatrade", "manual": "Added manually"}


class Review(TimestampMixin, db.Model):
    __tablename__ = "reviews"
    __table_args__ = (db.UniqueConstraint("account_id", "source", "external_id", name="uq_review_external"),)
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False, default="hapitech")
    external_id = db.Column(db.String(200))            # Google review id, or a stable import key
    source_url = db.Column(db.String(500))
    author_name = db.Column(db.String(120), nullable=False)
    rating = db.Column(db.Integer, nullable=False)     # 1–5
    body = db.Column(db.Text, nullable=False, default="")
    photos = db.Column(db.Text, nullable=False, default="[]")   # JSON list: media ids or "static:..." paths
    service = db.Column(db.String(120))
    town = db.Column(db.String(120))
    reviewed_at = db.Column(db.DateTime)   # when the customer wrote it; None = unknown (e.g. imported)
    status = db.Column(db.String(20), nullable=False, default="published")  # pending|published|reported|removed
    verified = db.Column(db.Boolean, nullable=False, default=False)      # came through a request link
    report_reason = db.Column(db.Text)
    request_id = db.Column(db.Integer, db.ForeignKey("review_requests.id"))
    sort_hint = db.Column(db.Integer, nullable=False, default=0)        # keeps imported order stable
    photo_count = db.Column(db.Integer, nullable=False, default=0)      # photos on the original (e.g. Google)
    price_tag = db.Column(db.String(30))                                 # Google's "Great price" / "Overpriced" etc.
    recommends = db.Column(db.Boolean)                                  # Facebook: recommends / doesn't (no stars there)
    account = db.relationship("Account")
    replies = db.relationship("ReviewReply", lazy=True, cascade="all, delete-orphan",
                              order_by="ReviewReply.created_at")

    @property
    def source_label(self):
        return REVIEW_SOURCES.get(self.source, self.source.title())

    @property
    def external(self):
        """Copied from another site (Google, Facebook…): the text and the owner's reply live there, so they're read-only."""
        return self.source in ("google", "facebook", "checkatrade")

    @property
    def truncated(self):
        return (self.body or "").rstrip().endswith("…")

    @property
    def link(self):
        """Where "via …" goes. Google reviews open the client's Google reviews page, never the write-a-review form."""
        if self.source == "google" and self.account and self.account.google_reviews_url:
            return self.account.google_reviews_url
        return self.source_url

    @property
    def reply(self):
        return self.replies[-1] if self.replies else None


class ReviewReply(db.Model):
    __tablename__ = "review_replies"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("reviews.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class ReviewRequest(db.Model):
    __tablename__ = "review_requests"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(255))                # phone or email (optional for QR/link)
    job_ref = db.Column(db.String(160))
    token = db.Column(db.String(48), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_urlsafe(18))
    sent_via = db.Column(db.String(20), nullable=False, default="link")   # sms|whatsapp|email|qr|link
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    opened_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    reminder_sent_at = db.Column(db.DateTime)
    account = db.relationship("Account")

    @property
    def state(self):
        if self.completed_at:
            return "done"
        if self.opened_at:
            return "opened"
        return "sent"


class ReviewSource(db.Model):
    """A connected external review platform (Phase 7: Google Business Profile, Facebook)."""
    __tablename__ = "review_sources"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)            # google | facebook
    external_account_id = db.Column(db.String(200))
    oauth_token_enc = db.Column(db.Text)
    last_synced_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default="disconnected")
