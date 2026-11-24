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


def admin_counts():
    """Badges for the admin menu (also used when HapiTech's own Jobs etc. are shown inside admin)."""
    from models.core import ChangeRequest
    from models.reviews import Review
    counts = {"reported": Review.query.filter_by(status="reported").count() or None,
              "requests": ChangeRequest.query.filter_by(status="new").count() or None}
    from models.work import Lead
    counts["issues"] = Lead.query.filter_by(source="issue", status="new", archived_at=None).count() or None
    from utils.hapitech_account import get as _ht
    ht = _ht(create=False)
    counts["my_jobs"] = (Lead.query.filter_by(account_id=ht.id, status="new", archived_at=None).count() or None) if ht else None
    from models.tasks import due_count, fresh_accepted
    counts["tasks"] = (due_count() + len(fresh_accepted())) or None
    if ht:      # your jobs needing action: new enquiries + accepted quotes still waiting for a task / date
        counts["my_jobs"] = (Lead.query.filter(Lead.account_id == ht.id, Lead.status == "new",
                                               Lead.archived_at.is_(None)).count() or None)
    return counts


@admin_bp.context_processor
def _shell():
    from utils.nav import admin_nav
    return {"area": "admin", "nav": admin_nav(admin_counts())}


from . import clients, reviews, lab, settings, tasks  # noqa: E402,F401
