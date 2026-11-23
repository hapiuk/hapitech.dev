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
        name = (f.get("name") or "").strip()[:120]
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
    name = "" if req.customer_name == "your customer" else req.customer_name
    return render_template("reviews/leave.html", a=a, req=req, f={"name": name}, error=None)


WRITE_LIMIT_PER_DAY = 3          # per visitor (hashed IP) per business
MIN_SECONDS_TO_WRITE = 4         # bots submit instantly


def _save_review_photos(a, files, name):
    ids = []
    for up in files.getlist("photos")[:MAX_REVIEW_PHOTOS]:
        if up and up.filename:
            path, w, h = save_image(up, a, prefix="review")      # raises UploadError
            m = Media(account_id=a.id, file_path=path, width=w, height=h, alt=f"Photo from {name}'s review")
            db.session.add(m)
            db.session.flush()
            ids.append(m.id)
    return ids


PENDING_AUTO_PUBLISH_DAYS = 14


def _matches_customer(a, email):
    from models.core import Account, User
    from models.work import Lead
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    if a.kind == "internal":     # HapiTech's own reviews: our clients are the customers
        return (db.session.query(User.id).filter(db.func.lower(User.email) == email, User.account_id.isnot(None),
                                                 User.account_id != a.id).first() is not None
                or db.session.query(Account.id).filter(Account.kind == "client",
                                                       db.func.lower(Account.contact_email) == email).first() is not None)
    return db.session.query(Lead.id).filter(Lead.account_id == a.id, db.func.lower(Lead.email) == email,
                                            Lead.status.in_(["accepted", "booked", "done"])).first() is not None


def _tell_owner_pending(a, review):
    if not a.contact_email:
        return
    try:
        from utils import email_html
        from utils.links import public_url
        email_html.send(a.contact_email, f"New review from {review.author_name}: waiting for your OK",
                        heading="A new review is waiting for your OK",
                        lines=[f"{review.author_name} left a {review.rating}-star review from your website.",
                               "Approve it to show it on your site. Please approve every genuine review, good or bad. "
                               f"Only mark spam or fake ones. If you don't get to it, it goes live by itself after "
                               f"{PENDING_AUTO_PUBLISH_DAYS} days."],
                        box=[("Review", (review.body or "(no text)")[:300])],
                        button={"label": "Check the review", "url": public_url(url_for("portal.reviews", show="pending"))})
    except Exception as exc:
        print(f"[REVIEW_PENDING_NOTIFY] {exc}")


@reviews_public_bp.route("/reviews/<slug>/write", methods=["GET", "POST"])
def write(slug):
    """Open review form behind each client site's "Leave a review" button (no request link needed)."""
    from itsdangerous import BadSignature, URLSafeTimedSerializer
    from models.core import LoginAttempt
    from utils.security import ip_key
    a = Account.query.filter(Account.slug == slug, Account.kind.in_(["client", "internal"])).first()
    if not a or a.status == "archived":
        abort(404)
    if not a.has_addon():                       # add-on off: the button keeps working, straight to Google
        if a.google_profile_url:
            return redirect(a.google_profile_url)
        abort(404)
    signer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="review-form")
    if request.method == "POST":
        f = request.form
        try:
            started = signer.loads(f.get("t", ""), max_age=60 * 60 * 6)
        except BadSignature:
            started = None
        too_fast = started is None or (dt.datetime.utcnow().timestamp() - started) < MIN_SECONDS_TO_WRITE
        if f.get("website") or too_fast:        # honeypot filled / instant submit: pretend it worked
            return render_template("reviews/thanks.html", a=a, review=None, already=False)
        since = dt.datetime.utcnow() - dt.timedelta(days=1)
        recent = LoginAttempt.query.filter(LoginAttempt.kind == "review", LoginAttempt.ip == ip_key(),
                                           LoginAttempt.email == f"review:{a.slug}",
                                           LoginAttempt.created_at >= since).count()
        if recent >= WRITE_LIMIT_PER_DAY:
            return render_template("reviews/leave.html", a=a, req=None, f=f, open_form=True, t=f.get("t"),
                                   error="You've already left reviews today. Thank you!")
        try:
            rating = int(f.get("rating") or 0)
        except ValueError:
            rating = 0
        name = (f.get("name") or "").strip()[:120]
        err = ("Tap a star rating first." if not 1 <= rating <= 5 else "Add your name." if not name else None)
        if err:
            return render_template("reviews/leave.html", a=a, req=None, f=f, open_form=True, t=f.get("t"), error=err)
        try:
            photo_ids = _save_review_photos(a, request.files, name)
        except UploadError as e:
            return render_template("reviews/leave.html", a=a, req=None, f=f, open_form=True, t=f.get("t"), error=str(e))
        # Verified if the email matches one of this business's own customers; otherwise it waits for an OK.
        # The email is only used for this check and is never stored.
        verified = _matches_customer(a, f.get("email"))
        review = Review(account_id=a.id, source="website", author_name=name, rating=rating,
                        body=(f.get("body") or "").strip()[:3000], photos=json.dumps(photo_ids),
                        service=(f.get("service") or "").strip()[:120] or None,
                        status="published" if verified else "pending",
                        verified=verified, reviewed_at=dt.datetime.utcnow())
        db.session.add(review)
        db.session.add(LoginAttempt(ip=ip_key(), email=f"review:{a.slug}", kind="review", success=True))
        db.session.commit()
        if not verified:
            _tell_owner_pending(a, review)
        return render_template("reviews/thanks.html", a=a, review=review, already=False)
    return render_template("reviews/leave.html", a=a, req=None, f={}, open_form=True,
                           t=signer.dumps(dt.datetime.utcnow().timestamp()), error=None)


@reviews_public_bp.route("/reviews/<slug>")
def business(slug):
    a = Account.query.filter(Account.slug == slug, Account.kind.in_(["client", "internal"])).first()
    if not a or a.status == "archived":
        abort(404)
    q = Review.query.filter(Review.account_id == a.id, Review.status.in_(["published", "reported"]))
    rows = q.order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all()
    avg = sum(r.rating for r in rows) / len(rows) if rows else None
    return render_template("reviews/business.html", a=a, rows=rows, avg=avg)
