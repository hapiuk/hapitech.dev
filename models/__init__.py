# models/__init__.py — shared SQLAlchemy instance + model registry.
# Import order matters only for relationship string resolution; all modules are imported here
# so Alembic autogenerate and create_all see every table.
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from . import core, content, reviews, bench  # noqa: E402,F401
from .core import Account, User, Job, Subscription, Payment, Note, AddOn, ChangeRequest, LoginAttempt  # noqa: E402,F401
from .content import Post, Media, ContentBlock, ContentBlockVersion  # noqa: E402,F401
from .reviews import Review, ReviewReply, ReviewRequest, ReviewSource  # noqa: E402,F401
from .bench import BenchModel, BenchPrompt, BenchRun, BenchResult  # noqa: E402,F401
