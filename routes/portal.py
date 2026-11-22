# routes/portal.py — the client portal (/portal) for Roland, Ray and future clients.
# Everything here is scoped to g.account via utils.security (owner_required + scoped()).
import datetime as dt
import json

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.content import ContentBlock, ContentBlockVersion, Media, Post
from models.core import ChangeRequest
from models.reviews import Review, ReviewReply, ReviewRequest
from utils.links import public_url, sms_href, whatsapp_href
from utils.mailer import send_email
from utils.security import owner_required, scoped
from utils.uploads import UploadError, delete_file, save_image

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")

MAX_POST_PHOTOS = 6


@portal_bp.context_processor
def _shell():
    from utils.nav import portal_nav
    if not getattr(g, "account", None):
        return {}
    unreplied = (Review.query.filter(Review.account_id == g.account.id, Review.status.in_(["published", "reported"]),
                                     ~Review.replies.any(), Review.reviewed_at.isnot(None)).count()) or None
    return {"area": "portal", "nav": portal_nav({"unreplied": unreplied}), "addon": g.account.addon()}


def addon_required(fn):
    """Reviews & Updates features: show the add-on page if it isn't switched on."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not g.account.has_addon():
            return render_template("portal/addon.html")
        return fn(*a, **kw)
    return wrapper


def _review_link(req: ReviewRequest) -> str:
    return public_url(url_for("reviews_public.leave", token=req.token))


def _request_message(req: ReviewRequest) -> str:
    who = g.account.contact_name or g.account.name
    return (f"Hi {req.customer_name}, thanks for choosing {g.account.name}! "
            f"Would you mind leaving {who.split()[0]} a quick review? It takes about 20 seconds: {_review_link(req)}")


# ---------------------------------------------------------------- home

@portal_bp.route("/")
@owner_required
def home():
    a = g.account
    month_start = dt.datetime.combine(dt.date.today().replace(day=1), dt.time())
    live = scoped(Review).filter(Review.status.in_(["published", "reported"]))
    stats = {
        "total": live.count(),
        "avg": db.session.query(db.func.avg(Review.rating)).filter(
            Review.account_id == a.id, Review.status.in_(["published", "reported"])).scalar(),
        "this_month": live.filter(Review.reviewed_at >= month_start).count(),
        "unreplied": live.filter(~Review.replies.any(), Review.reviewed_at.isnot(None)).count(),
        "waiting": scoped(ReviewRequest).filter(ReviewRequest.completed_at.is_(None)).count(),
    }
    last_post = scoped(Post, status="published").order_by(Post.published_at.desc()).first()
    latest = live.order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).limit(3).all()
    return render_template("portal/home.html", stats=stats, last_post=last_post, latest=latest)


# ---------------------------------------------------------------- ask for a review

@portal_bp.route("/ask", methods=["GET", "POST"])
@owner_required
@addon_required
def ask():
    if request.method == "POST":
        name = (request.form.get("customer_name") or "").strip()
        if not name:
            flash("Add the customer's first name so the message feels personal.", "err")
            return render_template("portal/ask.html", f=request.form)
        req = ReviewRequest(account_id=g.account.id, customer_name=name[:120],
                            contact=(request.form.get("contact") or "").strip()[:255] or None,
                            job_ref=(request.form.get("job_ref") or "").strip()[:160] or None,
                            created_by=current_user.id)
        db.session.add(req)
        db.session.commit()
        return redirect(url_for("portal.ask_send", rid=req.id))
    return render_template("portal/ask.html", f={})


@portal_bp.route("/ask/<int:rid>", methods=["GET", "POST"])
@owner_required
@addon_required
def ask_send(rid):
    req = scoped(ReviewRequest, id=rid).first_or_404()
    msg = _request_message(req)
    contact = req.contact or ""
    is_email = "@" in contact
    if request.method == "POST":           # "Email it for me"
        to = (request.form.get("email") or contact).strip()
        if "@" not in to:
            flash("Enter the customer's email address.", "err")
        else:
            try:
                send_email(to=to, subject=f"How did {g.account.name} do?", from_name=g.account.name,
                           reply_to=g.account.contact_email or None,
                           text=msg + f"\n\nThank you!\n{g.account.contact_name or g.account.name}")
                req.sent_via, req.contact = "email", to
                db.session.commit()
                flash(f"Email sent to {to}.", "ok")
            except Exception as exc:
                flash(f"The email couldn't be sent: {exc}", "err")
        return redirect(url_for("portal.ask_send", rid=rid))
    return render_template("portal/ask_send.html", req=req, msg=msg, link=_review_link(req), is_email=is_email,
                           sms=sms_href("" if is_email else contact, msg),
                           wa=whatsapp_href("" if is_email else contact, msg))


@portal_bp.route("/api/requests/<int:rid>/sent", methods=["POST"])
@owner_required
def ask_mark_sent(rid):
    req = scoped(ReviewRequest, id=rid).first_or_404()
    via = (request.get_json(silent=True) or {}).get("via")
    if via in ("sms", "whatsapp", "qr", "link"):
        req.sent_via = via
        if req.completed_at is None and request.args.get("reminder"):
            req.reminder_sent_at = dt.datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True})


@portal_bp.route("/requests")
@owner_required
@addon_required
def requests_list():
    rows = scoped(ReviewRequest).order_by(ReviewRequest.created_at.desc()).limit(200).all()
    stale = dt.datetime.utcnow() - dt.timedelta(days=5)
    return render_template("portal/requests.html", rows=rows, stale=stale)


# ---------------------------------------------------------------- reviews

@portal_bp.route("/reviews")
@owner_required
@addon_required
def reviews():
    show = request.args.get("show", "all")
    q = scoped(Review).filter(Review.status.in_(["published", "reported"]))
    if show == "unreplied":
        q = q.filter(~Review.replies.any(), Review.reviewed_at.isnot(None))
    rows = q.order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all()
    return render_template("portal/reviews.html", rows=rows, show=show)


@portal_bp.route("/reviews/<int:rid>", methods=["POST"])
@owner_required
@addon_required
def review_action(rid):
    r = scoped(Review, id=rid).first_or_404()
    action = request.form.get("action")
    if action == "reply":
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Write a reply first.", "err")
        else:
            for old in list(r.replies):
                db.session.delete(old)
            db.session.add(ReviewReply(review_id=r.id, body=body[:2000], author_id=current_user.id))
            flash("Reply saved. It shows under the review on your website.", "ok")
    elif action == "delete-reply":
        for old in list(r.replies):
            db.session.delete(old)
        flash("Reply removed.", "ok")
    elif action == "report":
        reason = (request.form.get("reason") or "").strip()
        if not reason:
            flash("Tell us briefly why this review should be checked.", "err")
        else:
            r.status, r.report_reason = "reported", reason[:1000]
            flash("Thanks. HapiTech will check it. It stays visible until then.", "ok")
    db.session.commit()
    return redirect(url_for("portal.reviews", show=request.args.get("show", "all")) + f"#r{r.id}")


# ---------------------------------------------------------------- posts

@portal_bp.route("/posts")
@owner_required
@addon_required
def posts():
    rows = scoped(Post).order_by(Post.updated_at.desc()).all()
    return render_template("portal/posts.html", rows=rows)


@portal_bp.route("/posts/new", methods=["GET", "POST"])
@portal_bp.route("/posts/<int:pid>", methods=["GET", "POST"])
@owner_required
@addon_required
def post_edit(pid=None):
    p = scoped(Post, id=pid).first_or_404() if pid else Post(account_id=g.account.id, author_id=current_user.id)
    if request.method == "POST":
        f = request.form
        if f.get("action") == "delete" and pid:
            for m in p.photos:
                delete_file(m.file_path)
                db.session.delete(m)
            db.session.delete(p)
            db.session.commit()
            flash("Post deleted.", "ok")
            return redirect(url_for("portal.posts"))
        p.title = (f.get("title") or "").strip()[:160]
        p.body = (f.get("body") or "").strip()[:5000]
        p.town = (f.get("town") or "").strip()[:120] or None
        if not p.title:
            flash("Give the post a short title, like \"New bathroom in Tettenhall\".", "err")
            if pid:
                db.session.rollback()
            return render_template("portal/post_form.html", p=p)
        keep = [int(i) for i in f.getlist("keep_photo") if i.isdigit()]
        photo_ids = [i for i in p.photo_id_list if i in keep]
        for m in p.photos:                         # photos the user unticked
            if m.id not in keep:
                delete_file(m.file_path)
                db.session.delete(m)
        errors = []
        for up in request.files.getlist("photos"):
            if not up or not up.filename:
                continue
            if len(photo_ids) >= MAX_POST_PHOTOS:
                errors.append(f"Only {MAX_POST_PHOTOS} photos per post. The rest weren't added.")
                break
            try:
                path, w, h = save_image(up, g.account, prefix="post")
            except UploadError as e:
                errors.append(f"{up.filename}: {e}")
                continue
            m = Media(account_id=g.account.id, file_path=path, width=w, height=h, uploaded_by=current_user.id,
                      alt=p.title or None)
            db.session.add(m)
            db.session.flush()
            photo_ids.append(m.id)
        p.photo_ids = json.dumps(photo_ids)
        publish = f.get("action") == "publish"
        if publish and p.status != "published":
            p.status, p.published_at = "published", dt.datetime.utcnow()
        elif f.get("action") == "unpublish":
            p.status = "draft"
        if not pid:
            db.session.add(p)
        db.session.commit()
        for e in errors:
            flash(e, "err")
        flash("Published. It appears on your website within 10 minutes." if p.status == "published"
              else "Saved as a draft.", "ok")
        return redirect(url_for("portal.posts"))
    return render_template("portal/post_form.html", p=p)


# ---------------------------------------------------------------- my website (content blocks)

@portal_bp.route("/website")
@owner_required
@addon_required
def website():
    blocks = scoped(ContentBlock).order_by(ContentBlock.group, ContentBlock.sort, ContentBlock.id).all()
    groups = {}
    for b in blocks:
        groups.setdefault(b.group, []).append(b)
    return render_template("portal/website.html", groups=groups)


@portal_bp.route("/website/<int:bid>", methods=["GET", "POST"])
@owner_required
@addon_required
def block_edit(bid):
    from utils.content_blocks import BlockError, parse_block_form
    b = scoped(ContentBlock, id=bid).first_or_404()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "undo":
            prev = ContentBlockVersion.query.filter_by(block_id=b.id).order_by(ContentBlockVersion.saved_at.desc()).first()
            if prev:
                b.value = prev.value
                db.session.delete(prev)
                flash("Change undone.", "ok")
        elif action == "reset":
            db.session.add(ContentBlockVersion(block_id=b.id, value=b.value, saved_by=current_user.id))
            b.value = b.default_value
            flash("Back to the original text.", "ok")
        else:
            try:
                new_value = parse_block_form(b, request.form, request.files, g.account, current_user)
            except BlockError as e:
                flash(str(e), "err")
                return render_template("portal/block_form.html", b=b)
            if new_value != b.value:
                db.session.add(ContentBlockVersion(block_id=b.id, value=b.value, saved_by=current_user.id))
                b.value, b.updated_by = new_value, current_user.id
            flash("Saved. Your website updates within 10 minutes.", "ok")
        db.session.commit()
        return redirect(url_for("portal.website") + f"#b{b.id}")
    return render_template("portal/block_form.html", b=b)


# ---------------------------------------------------------------- help, account

@portal_bp.route("/help", methods=["GET", "POST"])
@owner_required
def help():
    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Describe the change you'd like.", "err")
        else:
            cr = ChangeRequest(account_id=g.account.id, body=body[:5000], created_by=current_user.id)
            db.session.add(cr)
            db.session.commit()
            try:
                send_email(to="aaron@hapitech.dev", subject=f"Change request: {g.account.name}",
                           text=f"{current_user.name or current_user.email} asked for:\n\n{body}\n\n"
                                f"{public_url(url_for('admin.change_requests'))}")
            except Exception as exc:
                print(f"[CHANGE_REQUEST_EMAIL_ERROR] {exc}")
            flash("Sent to HapiTech. Aaron will be in touch.", "ok")
        return redirect(url_for("portal.help"))
    rows = scoped(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(20).all()
    return render_template("portal/help.html", rows=rows)


@portal_bp.route("/account", methods=["GET", "POST"])
@owner_required
def account():
    if request.method == "POST":
        if current_user.is_admin:
            flash("You're viewing as the client. Change your own password in Admin → Settings.", "err")
            return redirect(url_for("portal.account"))
        cur, new, new2 = (request.form.get(k, "") for k in ("current", "new", "new2"))
        if not current_user.check_password(cur):
            flash("Your current password isn't right.", "err")
        elif len(new) < 10:
            flash("Use at least 10 characters.", "err")
        elif new != new2:
            flash("The new passwords don't match.", "err")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed.", "ok")
        return redirect(url_for("portal.account"))
    return render_template("portal/account.html")
