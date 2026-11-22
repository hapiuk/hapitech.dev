# routes/admin/reviews.py — every client's reviews in one place: moderation + manual imports.
import datetime as dt

from flask import abort, flash, redirect, render_template, request, url_for

from models import db
from models.core import Account
from models.reviews import REVIEW_SOURCES, Review
from utils.security import safe_next

from . import admin_bp


@admin_bp.route("/reviews")
def reviews():
    status = request.args.get("status", "reported")
    acct = request.args.get("client")
    q = Review.query
    if status != "all":
        q = q.filter_by(status=status)
    if acct:
        a = Account.query.filter_by(slug=acct).first()
        q = q.filter_by(account_id=a.id if a else -1)
    rows = q.order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).limit(300).all()
    counts = dict(db.session.query(Review.status, db.func.count()).group_by(Review.status).all())
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    return render_template("admin/reviews.html", rows=rows, status=status, counts=counts, clients=clients,
                           client=acct, sources=REVIEW_SOURCES)


@admin_bp.route("/reviews/<int:rid>", methods=["POST"])
def review_set(rid):
    r = db.session.get(Review, rid) or abort(404)
    action = request.form.get("action")
    if action == "publish":
        r.status, r.report_reason = "published", None
        flash("Review is showing again.", "ok")
    elif action == "remove":
        r.status = "removed"
        flash("Review removed from public view (kept on record).", "ok")
    db.session.commit()
    return redirect(safe_next(request.form.get("back")) or url_for("admin.reviews"))


@admin_bp.route("/reviews/new", methods=["GET", "POST"])
def review_new():
    """Add a review by hand, e.g. from a Google / Checkatrade screenshot the client sent."""
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    if request.method == "POST":
        f = request.form
        a = Account.query.filter_by(slug=f.get("client")).first()
        try:
            rating = int(f.get("rating") or 0)
        except ValueError:
            rating = 0
        if not a or not (1 <= rating <= 5) or not (f.get("author_name") or "").strip():
            flash("Choose a client, a rating of 1–5 and the reviewer's name.", "err")
            return render_template("admin/review_form.html", clients=clients, f=f, sources=REVIEW_SOURCES)
        when = f.get("reviewed_at")
        r = Review(account_id=a.id, source=f.get("source") if f.get("source") in REVIEW_SOURCES else "manual",
                   source_url=(f.get("source_url") or "").strip() or a.google_profile_url,
                   author_name=f["author_name"].strip()[:120], rating=rating, body=(f.get("body") or "").strip(),
                   service=(f.get("service") or "").strip() or None, town=(f.get("town") or "").strip() or None,
                   reviewed_at=dt.datetime.fromisoformat(when) if when else None,
                   status="published", verified=False)
        db.session.add(r)
        db.session.commit()
        flash(f"Review added to {a.name}.", "ok")
        return redirect(url_for("admin.client", slug=a.slug, tab="reviews"))
    return render_template("admin/review_form.html", clients=clients, f={"client": request.args.get("client"),
                                                                          "source": "google"},
                           sources=REVIEW_SOURCES)
