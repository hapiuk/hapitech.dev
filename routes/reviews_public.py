# routes/reviews_public.py — what customers see: the review form behind a request link,
# each business's public review page, and uploaded media files.
import datetime as dt
import json

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for

from models import db
from models.content import Media
from models.core import Account
from models.reviews import Review, ReviewRequest
from utils.uploads import UploadError, save_image

reviews_public_bp = Blueprint("reviews_public", __name__)

MAX_REVIEW_PHOTOS = 3


@reviews_public_bp.route("/media/<path:path>")
def media_file(path):
    resp = send_from_directory(current_app.config["UPLOAD_ROOT"], path, max_age=60 * 60 * 24 * 30)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@reviews_public_bp.route("/r/<token>", methods=["GET", "POST"])
def leave(token):
    req = ReviewRequest.query.filter_by(token=token).first()
    if not req or req.account.status == "archived":
        abort(404)
    a = req.account
    if req.completed_at:
        review = Review.query.filter_by(request_id=req.id).first()
        return render_template("reviews/thanks.html", a=a, review=review, already=True)
    if req.opened_at is None:
        req.opened_at = dt.datetime.utcnow()
        db.session.commit()
    if request.method == "POST":
        f = request.form
        try:
            rating = int(f.get("rating") or 0)
        except ValueError:
            rating = 0
        name = (f.get("name") or req.customer_name or "").strip()[:120]
        if not (1 <= rating <= 5):
            return render_template("reviews/leave.html", a=a, req=req, f=f, error="Tap a star rating first.")
        if not name:
            return render_template("reviews/leave.html", a=a, req=req, f=f, error="Add your name.")
        photo_ids = []
        for up in request.files.getlist("photos")[:MAX_REVIEW_PHOTOS]:
            if up and up.filename:
                try:
                    path, w, h = save_image(up, a, prefix="review")
                except UploadError as e:
                    return render_template("reviews/leave.html", a=a, req=req, f=f, error=str(e))
                m = Media(account_id=a.id, file_path=path, width=w, height=h, alt=f"Photo from {name}'s review")
                db.session.add(m)
                db.session.flush()
                photo_ids.append(m.id)
        review = Review(account_id=a.id, source="hapitech", author_name=name, rating=rating,
                        body=(f.get("body") or "").strip()[:3000], photos=json.dumps(photo_ids),
                        service=req.job_ref, status="published", verified=True, request_id=req.id,
                        reviewed_at=dt.datetime.utcnow())
        req.completed_at = dt.datetime.utcnow()
        db.session.add(review)
        db.session.commit()
        return render_template("reviews/thanks.html", a=a, review=review, already=False)
    return render_template("reviews/leave.html", a=a, req=req, f={"name": req.customer_name}, error=None)


@reviews_public_bp.route("/reviews/<slug>")
def business(slug):
    a = Account.query.filter_by(slug=slug, kind="client").first()
    if not a or a.status == "archived":
        abort(404)
    q = Review.query.filter(Review.account_id == a.id, Review.status.in_(["published", "reported"]))
    rows = q.order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all()
    avg = sum(r.rating for r in rows) / len(rows) if rows else None
    return render_template("reviews/business.html", a=a, rows=rows, avg=avg)
