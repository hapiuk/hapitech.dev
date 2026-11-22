# models/content.py — what clients can change on their own sites: posts, photos, content blocks.
import datetime as dt
import json

from . import db
from .core import TimestampMixin, utcnow


class Media(db.Model):
    __tablename__ = "media"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    file_path = db.Column(db.String(300), nullable=False)        # relative to UPLOAD_ROOT
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    alt = db.Column(db.String(200))
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Post(TimestampMixin, db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    town = db.Column(db.String(120))
    photo_ids = db.Column(db.Text, nullable=False, default="[]")  # JSON list of Media ids, in order
    status = db.Column(db.String(20), nullable=False, default="draft")   # draft | published
    published_at = db.Column(db.DateTime)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    account = db.relationship("Account")
    author = db.relationship("User")

    @property
    def photo_id_list(self):
        try:
            return [int(i) for i in json.loads(self.photo_ids or "[]")]
        except (ValueError, TypeError):
            return []

    @property
    def photos(self):
        ids = self.photo_id_list
        if not ids:
            return []
        by_id = {m.id: m for m in Media.query.filter(Media.id.in_(ids), Media.account_id == self.account_id)}
        return [by_id[i] for i in ids if i in by_id]


BLOCK_TYPES = ("text", "longtext", "price", "images", "hours", "list")


class ContentBlock(db.Model):
    """One editable piece of a client site. `value` is JSON; its shape depends on `type`:
    text/longtext/price -> string, images -> [media_id|"static:path"], hours -> [[day, text]], list -> [str]."""
    __tablename__ = "content_blocks"
    __table_args__ = (db.UniqueConstraint("account_id", "key", name="uq_block_account_key"),)
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    key = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(20), nullable=False, default="text")
    label = db.Column(db.String(160), nullable=False)
    group = db.Column(db.String(80), nullable=False, default="General")
    help = db.Column(db.String(300))
    value = db.Column(db.Text, nullable=False, default='""')
    default_value = db.Column(db.Text, nullable=False, default='""')   # the site's original hard-coded text
    max_length = db.Column(db.Integer)
    sort = db.Column(db.Integer, nullable=False, default=0)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    versions = db.relationship("ContentBlockVersion", lazy=True, cascade="all, delete-orphan",
                               order_by="ContentBlockVersion.saved_at.desc()")

    @property
    def data(self):
        try:
            return json.loads(self.value)
        except ValueError:
            return self.value

    @property
    def is_default(self):
        return self.value == self.default_value


class ContentBlockVersion(db.Model):
    __tablename__ = "content_block_versions"
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey("content_blocks.id"), nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    saved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    saved_at = db.Column(db.DateTime, default=utcnow, nullable=False)
