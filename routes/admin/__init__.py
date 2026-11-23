# routes/admin — HapiTech admin (/admin). Every route is admin-only via the before_request guard.
from flask import Blueprint, abort, redirect, request, url_for
from flask_login import current_user

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
def _guard():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?") if request.method == "GET" else None))
    if not current_user.is_admin:
        abort(403)


@admin_bp.context_processor
def _shell():
    from models.core import ChangeRequest
    from models.reviews import Review
    from utils.nav import admin_nav
    counts = {"reported": Review.query.filter_by(status="reported").count() or None,
              "requests": ChangeRequest.query.filter_by(status="new").count() or None}
    from models.work import Lead
    counts["issues"] = Lead.query.filter_by(source="issue", status="new", archived_at=None).count() or None
    return {"area": "admin", "nav": admin_nav(counts)}


from . import clients, reviews, lab, settings  # noqa: E402,F401
