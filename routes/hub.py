# routes/hub.py — hapitech.report: an honest public reviews site for the businesses HapiTech works with.
# No logins. Every review is shown, good or bad; businesses can reply but can't edit or remove reviews.
# Anyone can report a review (it comes to Aaron) or leave one for a business.
# Served at hapitech.dev/rv/... and, once nginx points the domain here, at hapitech.report/... (see HubHost below).
import datetime as dt

from flask import Blueprint, abort, jsonify, render_template, request, url_for

from models import db
from models.core import Account
from models.reviews import Review

hub_bp = Blueprint("hub", __name__, url_prefix="/rv")
HUB_HOSTS = ("hapitech.report", "www.hapitech.report")


class HubHost:
    """WSGI middleware: on hapitech.report, /rolands-handyman is served by /rv/rolands-handyman.
    Shared paths (static files, photos, the review form, login/CSRF helpers) are left alone."""
    KEEP = ("/static/", "/media/", "/reviews/", "/auth/", "/app/", "/r/", "/rv/", "/favicon", "/robots.txt")

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        host = (environ.get("HTTP_X_FORWARDED_HOST") or environ.get("HTTP_HOST") or "").split(":")[0].lower()
        path = environ.get("PATH_INFO") or "/"
        if host in HUB_HOSTS and path != "/rv" and not path.startswith(self.KEEP):
            environ["PATH_INFO"] = "/rv" + path
        return self.app(environ, start_response)


def hub_url(endpoint, **kw):
    """url_for for hub pages, without the /rv prefix when we're on hapitech.report."""
    u = url_for(endpoint, **kw)
    if request.host.split(":")[0].lower() in HUB_HOSTS and (u == "/rv" or u.startswith("/rv/")):
        u = u[3:] or "/"
    return u


OWN = ("hapitech", "website", "manual")


def source_stats(a, rows):
    """Overall (every review, Facebook 'recommends' counted as 5★ / 'doesn't' as 1★), then each source."""
    g = [r for r in rows if r.source == "google"]
    f = [r for r in rows if r.source == "facebook"]
    h = [r for r in rows if r.source in OWN]
    out = {"overall": {"avg": sum(r.rating for r in rows) / len(rows) if rows else None, "count": len(rows)}}
    if g or a.google_rating:
        out["google"] = {"avg": float(a.google_rating) if a.google_rating else sum(r.rating for r in g) / len(g),
                         "count": a.google_count or len(g), "here": len(g), "url": a.google_reviews_url}
    if f or a.facebook_pct is not None:
        pct = a.facebook_pct if a.facebook_pct is not None else round(100 * sum(1 for r in f if r.recommends is not False) / len(f))
        out["facebook"] = {"pct": pct, "count": a.facebook_count or len(f), "here": len(f), "url": a.facebook_url}
    if h:
        out["hapitech"] = {"avg": sum(r.rating for r in h) / len(h), "count": len(h)}
    return out


def _businesses():
    """Client businesses with at least one public review, most reviewed first."""
    out = []
    for a in Account.query.filter(Account.kind == "client", Account.status == "active").all():
        rows = (Review.query.filter(Review.account_id == a.id, Review.status.in_(["published", "reported"]))
                .order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all())
        if not rows:
            continue
        latest = next((r for r in rows if r.body and r.rating >= 4 and len(r.body) > 60), rows[0])
        out.append({"a": a, "count": len(rows), "avg": sum(r.rating for r in rows) / len(rows), "latest": latest,
                    "replied": sum(1 for r in rows if r.reply), "src": source_stats(a, rows)})
    return sorted(out, key=lambda b: -b["count"])


@hub_bp.before_request
def _count_visit():
    """hapitech.report page views (paths as people see them, without the internal /rv)."""
    if request.method == "GET" and request.endpoint in ("hub.home", "hub.business", "hub.policy", "hub.terms", "hub.privacy"):
        from utils.own_visits import count
        count("hapitech-reviews", request.path.removeprefix("/rv") or "/")


@hub_bp.route("/")
def home():
    biz = _businesses()
    total = sum(b["count"] for b in biz)
    avg = (sum(b["avg"] * b["count"] for b in biz) / total) if total else None
    ids = [b["a"].id for b in biz]
    live = (Review.query.filter(Review.account_id.in_(ids), Review.status.in_(["published", "reported"])).all() if ids else [])
    by_src = {"google": 0, "facebook": 0, "hapitech": 0}
    for r in live:
        by_src["hapitech" if r.source in OWN else r.source if r.source in by_src else "hapitech"] += 1
    replied = sum(1 for r in live if r.reply)
    wall = sorted([r for r in live if r.body and len(r.body) > 40 and r.rating >= 4],
                  key=lambda r: r.reviewed_at or r.created_at, reverse=True)[:18]
    import re as _re
    picks = []
    for b in biz:                                   # quick-pick words in the search box: towns, then trade words
        for w in [b["a"].town] + _re.split(r"[^A-Za-z]+", b["a"].trade or ""):
            if w and len(w) > 3 and w.lower() not in ("and", "home", "services") and w.capitalize() not in picks:
                picks.append(w.capitalize() if w.islower() else w)
    return render_template("hub/home.html", biz=biz, total=total, avg=avg, by_src=by_src, wall=wall, picks=picks[:8],
                           reply_rate=round(100 * replied / len(live)) if live else 0)


@hub_bp.route("/<slug>")
def business(slug):
    a = Account.query.filter(Account.slug == slug, Account.kind.in_(["client", "internal"])).first()
    if not a or a.status == "archived":
        abort(404)
    rows = (Review.query.filter(Review.account_id == a.id, Review.status.in_(["published", "reported"]))
            .order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all())
    avg = sum(r.rating for r in rows) / len(rows) if rows else None
    dist = {n: sum(1 for r in rows if r.rating == n) for n in (5, 4, 3, 2, 1)}
    sources = {}
    for r in rows:
        sources[r.source_label] = sources.get(r.source_label, 0) + 1
    return render_template("hub/business.html", a=a, rows=rows, avg=avg, dist=dist, sources=sources,
                           replied=sum(1 for r in rows if r.reply), src=source_stats(a, rows),
                           by_source={k: sum(1 for r in rows if (r.source in OWN if k == "hapitech" else r.source == k))
                                      for k in ("google", "facebook", "hapitech")})


@hub_bp.route("/report/<int:rid>", methods=["POST"])
def report(rid):
    """Anyone can flag a review. It stays up while Aaron looks into it; he decides, not the business."""
    from models.core import LoginAttempt
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    from utils.security import ip_key
    r = db.session.get(Review, rid) or abort(404)
    d = request.get_json(silent=True) or {}
    reason = (d.get("reason") or "").strip()[:60]
    details = (d.get("details") or "").strip()[:2000]
    email = (d.get("email") or "").strip()[:200]
    if not reason:
        return jsonify({"ok": False, "message": "Choose a reason."}), 400
    since = dt.datetime.utcnow() - dt.timedelta(hours=1)
    if LoginAttempt.query.filter(LoginAttempt.kind == "review-report", LoginAttempt.ip == ip_key(),
                                 LoginAttempt.created_at >= since).count() >= 5:
        return jsonify({"ok": False, "message": "Thanks, we've had a few reports from you already. We'll look into them."}), 429
    db.session.add(LoginAttempt(ip=ip_key(), email=f"report:{rid}", kind="review-report", success=True))
    if r.status == "published":
        r.status = "reported"            # still shown: nothing comes down until it's been checked
    r.report_reason = f"{reason}: {details}"[:2000] if details else reason
    ht = hapitech()
    lead = Lead(account_id=ht.id, source="report", for_account_id=r.account_id, name=email or "Anonymous visitor",
                email=email or None, title=f"Review report: {r.account.name} · {r.author_name}"[:160],
                message=f"Reason: {reason}\n\n{details or '(no details)'}\n\n— The review ({r.rating}★, {r.source_label}):\n{r.body or '(no text)'}")
    db.session.add(lead)
    db.session.commit()
    try:
        from utils import email_html
        from utils.links import public_url
        email_html.send("aaron@hapitech.dev", f"Review reported on hapitech.report: {r.account.name}",
                        heading="Someone reported a review",
                        lines=[f"A visitor reported {r.author_name}'s {r.rating}★ review of {r.account.name}.",
                               "It stays visible until you've looked into it."],
                        box=[("Reason", reason), ("Details", details or "—"), ("Their email", email or "not given"),
                             ("Review", (r.body or "(no text)")[:300])],
                        button={"label": "Open it in admin", "url": public_url(url_for("admin.reviews", status="reported"))},
                        reply_to=email or None)
    except Exception as exc:
        print(f"[HUB_REPORT_NOTIFY] {exc}")
    return jsonify({"ok": True, "message": "Thanks. Aaron at HapiTech will look into it. Reviews are only removed if they break our review policy."})


@hub_bp.route("/policy")
def policy():
    return render_template("hub/policy.html")


@hub_bp.route("/terms")
def terms():
    return render_template("terms.html")


@hub_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")
