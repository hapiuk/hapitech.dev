# routes/public.py — public marketing pages and the contact form.
import datetime

from flask import Blueprint, jsonify, redirect, render_template, request
from flask_login import current_user

from utils.mailer import send_contact_email

public_bp = Blueprint("public", __name__)


@public_bp.before_request
def _count_visit():
    """hapitech.dev page views, like the client sites (not the contact form or anything posted)."""
    if request.method == "GET" and request.endpoint in ("public.index", "public.updates", "public.privacy", "public.terms", "public.post_link"):
        from utils.own_visits import count
        count("hapitech", request.path)


@public_bp.route("/")
def index():
    from utils.news import get_news
    # never block the homepage on feeds: empty list (section hidden) until a cache exists
    news_items, seen = [], set()
    for item in get_news(blocking=False).get("items", []):   # newest first, one per source
        if item.get("source_id") not in seen:
            seen.add(item.get("source_id"))
            news_items.append(item)
        if len(news_items) == 3:
            break
    return render_template("home.html", news_items=news_items, updates=_updates(3), reviews=_reviews(6))


@public_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@public_bp.route("/terms")
def terms():
    return render_template("terms.html")


@public_bp.route("/contact", methods=["POST"])
def contact():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:255]
    message = (data.get("message") or "").strip()[:5000]
    if not (name and email and message):
        return jsonify({"success": False, "message": "All fields required"}), 400
    meta = {
        "client": (data.get("client") or "").strip()[:80],
        "host": request.host,
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "ua": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
        "utc": datetime.datetime.utcnow().isoformat(),
    }
    _save_enquiry(name, email, message, data)
    try:
        send_contact_email(name=name, email=email, message=message, meta=meta)
    except Exception as e:
        print(f"[CONTACT_EMAIL_ERROR] {e}")
        return jsonify({"success": False, "message": "Could not send right now. Try again shortly."}), 500
    return jsonify({"success": True, "message": "Sent — we’ll get back to you shortly."})



# ---------------------------------------------------------------- HapiTech's own updates + reviews

def _updates(limit=None):
    from models.content import Post
    from utils.hapitech_account import get
    a = get(create=False)
    if not a:
        return []
    q = Post.query.filter_by(account_id=a.id, status="published").order_by(Post.published_at.desc())
    return q.limit(limit).all() if limit else q.all()


def _reviews(limit=6):
    from models.reviews import Review
    from utils.hapitech_account import get
    a = get(create=False)
    if not a:
        return []
    return (Review.query.filter_by(account_id=a.id, status="published")
            .order_by(Review.reviewed_at.desc().nullslast(), Review.created_at.desc()).limit(limit).all())


@public_bp.route("/updates")
@public_bp.route("/updates/<int:pid>")
def updates(pid=None):
    from flask import abort, url_for
    rows = _updates()
    post = None
    if pid is not None:
        post = next((p for p in rows if p.id == pid), None)
        if post is None:
            abort(404)
    return render_template("site/updates.html", rows=rows, post=post)


@public_bp.route("/posts/<int:pid>")
def post_link(pid):
    """The dashboard's share links use /posts/<id> on every site; on hapitech.dev those are /updates/<id>."""
    from flask import url_for
    return redirect(url_for("public.updates", pid=pid), code=301)


def _save_enquiry(name, email, message, data):
    """hapitech.dev enquiries also land in HapiTech's own Jobs (spam kept out), ready to quote or turn into a client."""
    try:
        from models import db
        from models.work import Lead
        from utils.hapitech_account import get
        from utils.spam import looks_like_spam
        need = (data.get("need") or "").strip()[:80]
        business = (data.get("business") or "").strip()[:160]
        lead = Lead(account_id=get().id, source="enquiry", name=name, email=email,
                    phone=(data.get("phone") or "").strip()[:40] or None,
                    title=(f"{need}" + (f" for {business}" if business else ""))[:160] or "Website enquiry",
                    message=message, notes=f"Business: {business}" if business else None)
        spam = looks_like_spam(name, email, message)
        if spam:
            lead.status, lead.notes = "spam", f"Blocked as spam: {spam}"
        db.session.add(lead)
        db.session.commit()
    except Exception as exc:          # never lose the email over this
        print(f"[ENQUIRY_SAVE] {exc}")
