# routes/portal.py — the client portal (/portal) for Roland, Ray and future clients.
# Everything here is scoped to g.account via utils.security (owner_required + scoped()).
import datetime as dt
import json

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.content import ContentBlock, ContentBlockVersion, Media, Post
from models.core import ChangeRequest
from models.reviews import REVIEW_SOURCES, Review, ReviewReply, ReviewRequest
from utils.links import public_url
from utils.mailer import send_email
from utils.security import owner_required, scoped
from utils.uploads import UploadError, delete_file, save_image

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")

MAX_POST_PHOTOS = 6

TIPS = [
    "Posting photos of finished jobs keeps your website fresh, and Google tends to show fresh websites higher.",
    "Mention the town in your posts, like “New bathroom in Tettenhall”. It helps local people find you on Google.",
    "Every new review helps. Ask at the end of each job, while the customer is happy with the work.",
    "Reply to your reviews, even with a quick thank-you. New customers read the replies too.",
    "Reviews on Google count most for “near me” searches. After someone reviews you here, we offer them a one-tap way to post it on Google too.",
    "Share your posts on Facebook and Instagram. Every share sends people back to your website.",
    "Keep your photos up to date. You can put your best (or most-liked) photos at the top of your homepage.",
    "Going on holiday? Turn on Away mode in Settings so customers know when you're back.",
    "Send quotes from your dashboard. Customers can accept with one tap, and it goes straight into your calendar.",
]


@portal_bp.context_processor
def _shell():
    from utils.nav import portal_nav
    if not getattr(g, "account", None):
        return {}
    unreplied = (Review.query.filter(Review.account_id == g.account.id, Review.status.in_(["published", "reported"]),
                                     ~Review.replies.any(), Review.reviewed_at.isnot(None), Review.reply_skipped_at.is_(None)).count()
                 + Review.query.filter_by(account_id=g.account.id, status="pending").count()) or None
    from models.work import Lead
    new_jobs = Lead.query.filter_by(account_id=g.account.id, status="new", archived_at=None).count() or None   # spam has its own status
    return {"area": "portal", "nav": portal_nav({"unreplied": unreplied, "new_jobs": new_jobs},
                                                owner=current_user.is_owner, features=g.account.feature_set),
            "addon": g.account.addon(), "brand_accent": brand_accent(g.account)}


def brand_accent(account):
    """The client's brand colour for their dashboard accent, only if it's a plain #rrggbb (it goes into CSS)."""
    import re
    c = (account.brand_colour or "").strip()
    return c.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else None


@portal_bp.after_request
def _remember_app(resp):
    """Remember which client's dashboard this device uses, so the installed app's login shows their logo."""
    acc = getattr(g, "account", None)
    if acc is not None and getattr(acc, "slug", None) and request.cookies.get("ht_app") != acc.slug:
        resp.set_cookie("ht_app", acc.slug, max_age=60 * 60 * 24 * 365, samesite="Lax", secure=request.is_secure, httponly=True)
    return resp


@portal_bp.route("/login")
def login():
    """The installed app's own login page (inside /portal/, so the app never jumps out to the browser).
    Branded for the client whose app this is; after the code, straight back to their dashboard."""
    from models.core import Account
    from utils.security import safe_next
    slug = request.args.get("app") or request.cookies.get("ht_app")
    acc = Account.query.filter(Account.slug == slug, Account.kind.in_(["client", "internal"])).first() if slug else None
    nxt = safe_next(request.args.get("next"))
    if not (nxt or "").startswith("/portal"):
        nxt = f"/portal/?app={acc.slug}" if acc else "/portal/"
    if current_user.is_authenticated:
        return redirect(nxt if (current_user.is_admin or current_user.account_id) else "/")
    return render_template("auth/app_login.html", acc=acc, next=nxt, brand=brand_accent(acc) if acc else None)


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
    hi = f"Hi {req.customer_name}, thanks" if req.customer_name != "your customer" else "Thanks"
    return (f"{hi} for choosing {g.account.name}! "
            f"Would you mind leaving {who.split()[0]} a quick review? It takes about 20 seconds: {_review_link(req)}")


# ---------------------------------------------------------------- home

def reply_rate(account, since):
    """% of reviews received since `since` that have a reply (None if there weren't any)."""
    rows = Review.query.filter(Review.account_id == account.id, Review.status.in_(["published", "reported"]),
                               db.func.coalesce(Review.reviewed_at, Review.created_at) >= dt.datetime.combine(since, dt.time())).all()
    if not rows:
        return None
    return round(100 * sum(1 for r in rows if r.replies) / len(rows))


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
        "unreplied": live.filter(~Review.replies.any(), Review.reviewed_at.isnot(None), Review.reply_skipped_at.is_(None)).count(),
        "waiting": scoped(ReviewRequest).filter(ReviewRequest.completed_at.is_(None)).count(),
    }
    last_post = scoped(Post, status="published").order_by(Post.published_at.desc()).first()
    stats["pending"] = scoped(Review, status="pending").count()
    stats["rate_year"], stats["rate_month"] = reply_rate(a, dt.date(dt.date.today().year, 1, 1)), reply_rate(a, dt.date.today().replace(day=1))
    from utils.traffic import summary
    return render_template("portal/home.html", stats=stats, last_post=last_post, t=summary(a), tips=TIPS,
                           tip_start=dt.date.today().timetuple().tm_yday % len(TIPS))


# ---------------------------------------------------------------- ask for a review

@portal_bp.route("/ask", methods=["GET", "POST"])
@owner_required
@addon_required
def ask():
    """Job done: make a single-use review link, then show it as a QR code (or email it)."""
    if request.method == "POST":
        req = ReviewRequest(account_id=g.account.id,
                            customer_name=(request.form.get("customer_name") or "").strip()[:120] or "your customer",
                            job_ref=(request.form.get("job_ref") or "").strip()[:160] or None,
                            sent_via="qr", created_by=current_user.id)
        db.session.add(req)
        db.session.commit()
        return redirect(url_for("portal.ask_send", rid=req.id))
    return render_template("portal/ask.html", f={})


@portal_bp.route("/ask/<int:rid>", methods=["GET", "POST"])
@owner_required
@addon_required
def ask_send(rid):
    req = scoped(ReviewRequest, id=rid).first_or_404()
    if request.method == "POST" and request.form.get("action") == "remove":
        if req.completed_at:
            flash("They've already left a review, so this one stays.", "err")
        else:
            db.session.delete(req)
            db.session.commit()
            flash("Request removed. Its link no longer works.", "ok")
        return redirect(url_for("portal.reviews", show="sent"))
    if request.method == "POST" and request.form.get("action") == "renew":
        if req.completed_at:
            flash("They've already left a review.", "ok")
        else:
            req.renew()
            db.session.commit()
            flash(f"Fresh link made. It works for {ReviewRequest.LINK_DAYS} days. Send it the same way as before.", "ok")
        return redirect(url_for("portal.ask_send", rid=rid))
    if request.method == "POST":           # "Email them the link" (the address is used once, never stored)
        to = (request.form.get("email") or "").strip()
        if req.expired:
            req.renew()                    # never email a link that no longer works
        if "@" not in to or len(to) > 255:
            flash("Enter the customer's email address.", "err")
        else:
            try:
                from utils.client_mail import send_review_link
                send_review_link(g.account, to, _review_link(req),
                                 first_name=None if req.customer_name == "your customer" else req.customer_name)
                if req.sent_via == "email" and req.completed_at is None:
                    req.reminder_sent_at = dt.datetime.utcnow()
                req.sent_via = "email"
                db.session.commit()
                flash(f"Sent to {to}. We don't keep their email address.", "ok")
            except Exception as exc:
                flash(f"The email couldn't be sent: {exc}", "err")
        return redirect(url_for("portal.ask_send", rid=rid))
    return render_template("portal/ask_send.html", req=req, msg=_request_message(req), link=_review_link(req))


@portal_bp.route("/requests")
@owner_required
@addon_required
def requests_list():
    return redirect(url_for("portal.reviews", show="sent"))        # now the "Sent" tab on Your reviews


# ---------------------------------------------------------------- reviews

ADD_SOURCES = {k: REVIEW_SOURCES[k] for k in ("google", "facebook", "checkatrade", "manual")}
GOOGLE_SYNC_NOTE = ("Waiting on Google API access. Once it's approved, your Google reviews will come in by themselves "
                    "and you'll be able to reply to them from here. For now, copy them in by hand.")


@portal_bp.route("/reviews/add", methods=["GET", "POST"])
@owner_required
@addon_required
def review_add():
    """Admin only: copy in a review by hand. Clients ask Aaron instead (reviews are only added once checked)."""
    if not current_user.is_admin:
        flash("Reviews from other sites are added by Aaron once checked. Use \"Somewhere else?\" under Get reviewed in more places to ask.", "err")
        return redirect(url_for("portal.reviews"))
    f = request.form if request.method == "POST" else {"source": "google"}
    if request.method == "POST":
        try:
            rating = int(f.get("rating") or 0)
        except ValueError:
            rating = 0
        name = (f.get("author_name") or "").strip()[:120]
        if not (1 <= rating <= 5) or not name:
            flash("Add the reviewer's name and the number of stars.", "err")
        else:
            when = f.get("reviewed_at")
            try:
                when = dt.datetime.fromisoformat(when) if when else None
            except ValueError:
                when = None
            source = f.get("source") if f.get("source") in ADD_SOURCES else "manual"
            db.session.add(Review(account_id=g.account.id, source=source, author_name=name, rating=rating,
                                  body=(f.get("body") or "").strip()[:3000], reviewed_at=when,
                                  source_url=g.account.google_profile_url if source == "google" else None,
                                  external_id=f"added-by:{current_user.id}", status="published", verified=False))
            db.session.commit()
            flash("Review added. It shows on your website within 10 minutes.", "ok")
            return redirect(url_for("portal.reviews"))
    return render_template("portal/review_add.html", f=f, sources=ADD_SOURCES, note=GOOGLE_SYNC_NOTE)


@portal_bp.route("/reviews")
@owner_required
@addon_required
def reviews():
    show = request.args.get("show", "all")
    if show == "sent":                   # review requests: who's been asked, opened, reviewed, or whose link expired
        sent = scoped(ReviewRequest).order_by(ReviewRequest.created_at.desc()).limit(200).all()
        return render_template("portal/reviews.html", show=show, sent=sent, rows=[], pending=[], platforms=[], active=False,
                               stale=dt.datetime.utcnow() - dt.timedelta(days=5), link_days=ReviewRequest.LINK_DAYS)
    pending = scoped(Review, status="pending").order_by(Review.created_at.desc()).all()
    q = scoped(Review).filter(Review.status.in_(["published", "reported"]))
    if show == "unreplied":
        q = q.filter(~Review.replies.any(), Review.reviewed_at.isnot(None), Review.reply_skipped_at.is_(None))
    from utils import review_search
    q, active = review_search.apply(q, request.args)
    rows = q.all()
    from utils.review_platforms import for_account
    return render_template("portal/reviews.html", rows=rows, show=show, pending=pending, platforms=for_account(g.account),
                           active=active)


@portal_bp.route("/reviews/<int:rid>", methods=["POST"])
@owner_required
@addon_required
def review_action(rid):
    r = scoped(Review, id=rid).first_or_404()
    action = request.form.get("action")
    if action in ("reply", "delete-reply") and r.external:
        flash(f"This review is on {r.source_label}, so reply to it there. Replies from {r.source_label} show here automatically.", "err")
        return redirect(url_for("portal.reviews", show=request.args.get("show", "all")) + f"#r{r.id}")
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
    elif action == "skip-reply":
        r.reply_skipped_at = dt.datetime.utcnow()
        flash("Marked as no reply needed. It's out of your Needs a reply list.", "ok")
    elif action == "unskip-reply":
        r.reply_skipped_at = None
        flash("Back in your Needs a reply list.", "ok")
    elif action == "approve" and r.status == "pending":
        r.status = "published"
        flash("Approved. It shows on your website within 10 minutes.", "ok")
    elif action == "spam" and r.status == "pending":
        r.status, r.report_reason = "removed", "Marked as spam by the business"
        flash("Marked as spam. It won't be shown.", "ok")
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
            from utils.photos import remove_from_gallery
            remove_from_gallery(g.account, [m.id for m in p.photos], current_user.id)
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
        from utils.photos import add_to_gallery, remove_from_gallery
        remove_from_gallery(g.account, [m.id for m in p.photos if m.id not in keep], current_user.id)
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
        added = 0
        if p.status == "published" and f.get("to_gallery"):
            added = add_to_gallery(g.account, photo_ids, current_user.id)
        db.session.commit()
        if added:
            flash(f"{added} photo{'s' if added != 1 else ''} added to your website gallery too.", "ok")
        for e in errors:
            flash(e, "err")
        if p.status == "published":
            flash("Published. It appears on your website within 10 minutes. Now share it!" if publish
                  else "Saved.", "ok")
            return redirect(url_for("portal.post_edit", pid=p.id) + "#share")
        flash("Saved as a draft.", "ok")
        return redirect(url_for("portal.posts"))
    return render_template("portal/post_form.html", p=p)


# ---------------------------------------------------------------- my website (content blocks)

@portal_bp.route("/website")
@owner_required
@addon_required
def website():
    if not current_user.is_owner:
        flash("Only the business owner can change the website.", "err")
        return redirect(url_for("portal.home"))
    from utils.photos import _block_keys, hero_mode, photo_src
    blocks = (scoped(ContentBlock).filter(ContentBlock.type != "setting")
              .order_by(ContentBlock.sort, ContentBlock.id).all())          # roughly the order they appear on the site
    photos, groups = [], {}
    for b in blocks:
        if b.type == "images":
            keys = _block_keys(g.account, b)
            photos.append({"b": b, "count": len(keys), "thumbs": [photo_src(g.account, k) for k in keys[:5]]})
            continue
        # one card per item: "services.kitchens.title" + "services.kitchens.text" edit together
        item = b.key.rsplit(".", 1)[0] if "." in b.key else b.key
        groups.setdefault(b.group, {}).setdefault(item, []).append(b)
    edited = sum(1 for b in blocks if not b.is_default)
    last = max((b.updated_at for b in blocks if not b.is_default), default=None)
    from utils import work_requests as wr
    return render_template("portal/website.html", photos=photos, groups=groups, edited=edited, total=len(blocks),
                           last=last, hero_mode=hero_mode(g.account),
                           work=wr.for_client(g.account), work_kinds=wr.KINDS, work_status=wr.CLIENT_STATUS)


@portal_bp.route("/website/save", methods=["POST"])
@owner_required
@addon_required
def website_save():
    """Save one card (e.g. a service's name + description) edited in place on the My website page."""
    from utils.content_blocks import BlockError, parse_block_form
    changed, anchor = 0, ""
    for field, raw in request.form.items():
        if not field.startswith("b") or not field[1:].isdigit():
            continue
        b = scoped(ContentBlock, id=int(field[1:])).first_or_404()
        if b.type not in ("text", "longtext", "price", "list"):
            continue
        anchor = anchor or f"#b{b.id}"
        try:
            new_value = parse_block_form(b, {"value": raw}, None, g.account, current_user)
        except BlockError as e:
            db.session.rollback()
            flash(f"{b.label}: {e}", "err")
            return redirect(url_for("portal.website") + anchor)
        if new_value != b.value:
            db.session.add(ContentBlockVersion(block_id=b.id, value=b.value, saved_by=current_user.id))
            b.value, b.updated_by = new_value, current_user.id
            changed += 1
    db.session.commit()
    flash("Saved. Your website updates within 10 minutes." if changed else "No changes to save.", "ok")
    return redirect(url_for("portal.website", saved=anchor[2:] or None) + anchor)


@portal_bp.route("/website/<int:bid>", methods=["GET", "POST"])
@owner_required
@addon_required
def block_edit(bid):
    if not current_user.is_owner:
        abort(403)
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
                from utils import email_html
                email_html.send("aaron@hapitech.dev", f"Change request: {g.account.name}",
                                heading=f"{g.account.name} asked for a change",
                                lines=[f"From {current_user.name or current_user.email}:", body],
                                button={"label": "Open change requests",
                                        "url": public_url(url_for("admin.change_requests"))})
            except Exception as exc:
                print(f"[CHANGE_REQUEST_EMAIL_ERROR] {exc}")
            flash("Sent to HapiTech. Aaron will be in touch.", "ok")
        return redirect(url_for("portal.help"))
    rows = scoped(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(20).all()
    return render_template("portal/help.html", rows=rows)


# ---------------------------------------------------------------- report an issue (every page)

@portal_bp.route("/issue", methods=["POST"])
@owner_required
def report_issue():
    """'Report an issue' on any dashboard page: lands in HapiTech's own Jobs, and Aaron gets an email."""
    import datetime as _dt
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    d = request.get_json(silent=True) or {}
    what = (d.get("what") or "").strip()[:3000]
    if not what:
        return jsonify({"ok": False, "message": "Tell us what went wrong."}), 400
    ht = hapitech()
    since = _dt.datetime.utcnow() - _dt.timedelta(hours=1)
    if Lead.query.filter(Lead.account_id == ht.id, Lead.source == "issue", Lead.email == current_user.email,
                         Lead.created_at >= since).count() >= 10:
        return jsonify({"ok": False, "message": "Thanks, we've got a few from you already. Aaron will be in touch."}), 429
    page, before = (d.get("page") or "")[:300], (d.get("before") or "")[:300]
    where = before if d.get("on_before") and before else page
    details = [what, "", f"Page: {where}"]
    if d.get("on_before") and page:
        details.append(f"(Reported from: {page})")
    elif before:
        details.append(f"Page before: {before}")
    details += [f"Device: {(d.get('device') or request.user_agent.string or '')[:300]}",
                f"Screen: {(d.get('screen') or '')[:40]}",
                f"Business: {g.account.name}  ·  Reported by {current_user.name or current_user.email}"]
    lead = Lead(account_id=ht.id, source="issue", name=f"{g.account.name}: issue",
                email=current_user.email, title=f"Issue on {where.split('?')[0][:120] or 'the dashboard'}",
                message="\n".join(details))
    db.session.add(lead)
    db.session.commit()
    try:
        from utils import email_html
        email_html.send("aaron@hapitech.dev", f"Issue reported: {g.account.name}", heading="Someone reported an issue",
                        lines=[f"{current_user.name or current_user.email} ({g.account.name}) says:", what],
                        box=[("Page", where or "-"), ("Device", (d.get("device") or "")[:120] or "-"),
                             ("Screen", d.get("screen") or "-"), ("Reply to", current_user.email)],
                        button={"label": "Open it in your jobs", "url": public_url(url_for("portal.job", lid=lead.id, **{"as": ht.slug}))},
                        reply_to=current_user.email)
    except Exception as exc:
        print(f"[ISSUE_NOTIFY] {exc}")
    return jsonify({"ok": True, "message": "Thanks! Aaron has been told and will look into it."})


from . import portal_work  # noqa: E402,F401  (jobs, quotes, invoices, calendar, settings)
