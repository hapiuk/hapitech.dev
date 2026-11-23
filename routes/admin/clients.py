# routes/admin/clients.py — overview, clients, jobs, money, notes, users, add-ons, site keys.
import datetime as dt
import secrets
from decimal import Decimal, InvalidOperation

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from models import db
from models.bench import BenchRun
from models.core import (JOB_STATUSES, JOB_TYPES, Account, AddOn, ChangeRequest, Job, Note, Payment,
                         Subscription, User, slugify)
from models.reviews import Review, ReviewRequest
from utils.security import safe_next

from . import admin_bp


def _money(v, default=Decimal("0")):
    try:
        return Decimal(str(v).replace("£", "").replace(",", "").strip() or "0").quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return default


def _date(v):
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _acct(slug) -> Account:
    a = Account.query.filter_by(slug=slug).first()
    if not a:
        abort(404)
    return a


# ---------------------------------------------------------------- overview

@admin_bp.route("/")
def home():
    today = dt.date.today()
    month_start = today.replace(day=1)
    paid_month = db.session.query(db.func.coalesce(db.func.sum(Payment.amount_gbp), 0)).filter(
        Payment.paid_at >= month_start).scalar()
    subs = Subscription.query.filter_by(status="active").all()
    mrr = sum(s.monthly_gbp for s in subs)
    overdue = [s for s in subs if s.next_due and s.next_due < today]
    due_soon = [s for s in subs if s.next_due and today <= s.next_due <= today + dt.timedelta(days=14)]
    unpaid_jobs = [j for j in Job.query.filter(Job.status == "done").all()
                   if float(j.price_gbp or 0) > 0 and not j.is_paid]
    active_jobs = Job.query.filter(Job.status.in_(["booked", "in_progress"])).order_by(Job.due_date).all()
    new_reviews = Review.query.filter(Review.reviewed_at >= dt.datetime.combine(month_start, dt.time())).count()
    open_requests = ReviewRequest.query.filter(ReviewRequest.completed_at.is_(None)).count()
    latest_run = BenchRun.query.order_by(BenchRun.created_at.desc()).first()
    clients = Account.query.filter(Account.kind == "client", Account.status != "archived").order_by(Account.name).all()
    changes = ChangeRequest.query.filter(ChangeRequest.status != "done").order_by(ChangeRequest.created_at.desc()).limit(5).all()
    return render_template("admin/home.html", paid_month=paid_month, mrr=mrr, overdue=overdue, due_soon=due_soon,
                           unpaid_jobs=unpaid_jobs, active_jobs=active_jobs, new_reviews=new_reviews,
                           open_requests=open_requests, latest_run=latest_run, clients=clients, changes=changes,
                           today=today, greeting=("Morning" if dt.datetime.now().hour < 12 else
                                                  "Afternoon" if dt.datetime.now().hour < 18 else "Evening"))


@admin_bp.route("/api/site-status")
def site_status():
    from utils.sitecheck import check_many
    domains = [a.domain for a in Account.query.filter(Account.domain.isnot(None), Account.status != "archived")]
    return jsonify({"ok": True, "sites": check_many(["hapitech.dev"] + domains)})


# ---------------------------------------------------------------- clients

@admin_bp.route("/clients")
def clients():
    show = request.args.get("show", "current")
    q = Account.query.filter_by(kind="client")
    q = q.filter(Account.status == "archived") if show == "archived" else q.filter(Account.status != "archived")
    rows = []
    for a in q.order_by(Account.name).all():
        rows.append({
            "a": a,
            "mrr": sum(s.monthly_gbp for s in a.subscriptions if s.status == "active"),
            "paid": sum(float(p.amount_gbp or 0) for p in a.payments),
            "reviews": Review.query.filter_by(account_id=a.id, status="published").count(),
            "open_jobs": sum(1 for j in a.jobs if j.status in ("quote", "booked", "in_progress")),
        })
    return render_template("admin/clients.html", rows=rows, show=show)


ACCOUNT_FIELDS = ("name", "domain", "trade", "town", "contact_name", "contact_email", "contact_phone",
                  "google_profile_url", "logo_path", "brand_colour", "notes", "status")


def _fill_account(a: Account, form):
    for f in ACCOUNT_FIELDS:
        if f in form:
            setattr(a, f, (form.get(f) or "").strip() or None)
    a.name = a.name or "Untitled client"
    a.status = a.status or "active"
    if a.domain:
        a.domain = a.domain.replace("https://", "").replace("http://", "").strip("/").lower()


@admin_bp.route("/clients/new", methods=["GET", "POST"])
def client_new():
    if request.method == "POST":
        a = Account(kind="client")
        _fill_account(a, request.form)
        base, n, slug = slugify(a.name), 2, slugify(a.name)
        while Account.query.filter_by(slug=slug).first():
            slug, n = f"{base}-{n}", n + 1
        a.slug = slug
        db.session.add(a)
        db.session.commit()
        flash(f"{a.name} added.", "ok")
        return redirect(url_for("admin.client", slug=a.slug))
    return render_template("admin/client_form.html", a=None)


@admin_bp.route("/clients/<slug>/edit", methods=["GET", "POST"])
def client_edit(slug):
    a = _acct(slug)
    if request.method == "POST":
        _fill_account(a, request.form)
        db.session.commit()
        flash("Saved.", "ok")
        return redirect(url_for("admin.client", slug=a.slug))
    return render_template("admin/client_form.html", a=a)


@admin_bp.route("/clients/<slug>")
def client(slug):
    a = _acct(slug)
    tab = request.args.get("tab", "overview")
    reviews = Review.query.filter_by(account_id=a.id).order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all() if tab == "reviews" else []
    stats = {
        "paid": sum(float(p.amount_gbp or 0) for p in a.payments),
        "mrr": sum(s.monthly_gbp for s in a.subscriptions if s.status == "active"),
        "reviews": Review.query.filter_by(account_id=a.id, status="published").count(),
        "avg": db.session.query(db.func.avg(Review.rating)).filter_by(account_id=a.id, status="published").scalar(),
        "requests": ReviewRequest.query.filter_by(account_id=a.id).count(),
    }
    new_key = session.pop("new_site_key", None) if session.get("new_site_key_for") == a.slug else None
    traffic = None
    if tab == "traffic":
        from utils.traffic import summary
        traffic = summary(a)
    return render_template("admin/client.html", a=a, tab=tab, reviews=reviews, stats=stats,
                           job_types=JOB_TYPES, job_statuses=JOB_STATUSES, today=dt.date.today(), new_key=new_key,
                           t=traffic)


@admin_bp.route("/clients/<slug>/notes", methods=["POST"])
def note_add(slug):
    a = _acct(slug)
    body = (request.form.get("body") or "").strip()
    if body:
        db.session.add(Note(account_id=a.id, author_id=current_user.id, body=body[:5000]))
        db.session.commit()
    return redirect(url_for("admin.client", slug=slug))


# ---------------------------------------------------------------- jobs

@admin_bp.route("/clients/<slug>/jobs", methods=["POST"])
@admin_bp.route("/clients/<slug>/jobs/<int:job_id>", methods=["POST"])
def job_save(slug, job_id=None):
    a = _acct(slug)
    j = Job.query.filter_by(id=job_id, account_id=a.id).first_or_404() if job_id else Job(account_id=a.id)
    f = request.form
    if f.get("action") == "delete" and job_id:
        Payment.query.filter_by(job_id=j.id).update({"job_id": None})
        db.session.delete(j)
        db.session.commit()
        flash("Job deleted.", "ok")
        return redirect(url_for("admin.client", slug=slug, tab="jobs"))
    j.title = (f.get("title") or "").strip() or "Untitled job"
    j.type = f.get("type") if f.get("type") in dict(JOB_TYPES) else "other"
    j.status = f.get("status") if f.get("status") in dict(JOB_STATUSES) else "quote"
    j.price_gbp = _money(f.get("price_gbp"))
    j.due_date = _date(f.get("due_date"))
    j.notes = (f.get("notes") or "").strip() or None
    if not job_id:
        db.session.add(j)
    db.session.commit()
    flash("Job saved.", "ok")
    return redirect(url_for("admin.client", slug=slug, tab="jobs"))


# ---------------------------------------------------------------- money

@admin_bp.route("/clients/<slug>/subscriptions", methods=["POST"])
@admin_bp.route("/clients/<slug>/subscriptions/<int:sub_id>", methods=["POST"])
def sub_save(slug, sub_id=None):
    a = _acct(slug)
    s = Subscription.query.filter_by(id=sub_id, account_id=a.id).first_or_404() if sub_id else Subscription(account_id=a.id)
    f = request.form
    if f.get("action") == "delete" and sub_id:
        Payment.query.filter_by(subscription_id=s.id).update({"subscription_id": None})
        db.session.delete(s)
        db.session.commit()
        flash("Subscription removed.", "ok")
        return redirect(url_for("admin.client", slug=slug, tab="money"))
    s.title = (f.get("title") or "").strip() or "Subscription"
    s.amount_gbp = _money(f.get("amount_gbp"))
    s.interval = "yearly" if f.get("interval") == "yearly" else "monthly"
    s.next_due = _date(f.get("next_due"))
    s.status = f.get("status") if f.get("status") in ("active", "paused", "cancelled") else "active"
    if not sub_id:
        db.session.add(s)
    db.session.commit()
    flash("Subscription saved.", "ok")
    return redirect(url_for("admin.client", slug=slug, tab="money"))


@admin_bp.route("/clients/<slug>/payments", methods=["POST"])
def payment_add(slug):
    a = _acct(slug)
    f = request.form
    p = Payment(account_id=a.id, amount_gbp=_money(f.get("amount_gbp")), paid_at=_date(f.get("paid_at")) or dt.date.today(),
                method=(f.get("method") or "bank")[:30], ref=(f.get("ref") or "").strip()[:120] or None)
    if f.get("job_id"):
        p.job_id = Job.query.filter_by(id=int(f["job_id"]), account_id=a.id).first_or_404().id
    if f.get("subscription_id"):
        sub = Subscription.query.filter_by(id=int(f["subscription_id"]), account_id=a.id).first_or_404()
        p.subscription_id = sub.id
        if f.get("advance"):
            sub.advance()
    if p.amount_gbp <= 0:
        flash("Enter an amount above £0.", "err")
        return redirect(url_for("admin.client", slug=slug, tab="money"))
    db.session.add(p)
    db.session.commit()
    flash(f"Payment of £{p.amount_gbp:,.2f} recorded.", "ok")
    return redirect(safe_next(request.form.get("back")) or url_for("admin.client", slug=slug, tab="money"))


@admin_bp.route("/clients/<slug>/payments/<int:pid>/delete", methods=["POST"])
def payment_delete(slug, pid):
    a = _acct(slug)
    p = Payment.query.filter_by(id=pid, account_id=a.id).first_or_404()
    db.session.delete(p)
    db.session.commit()
    flash("Payment deleted.", "ok")
    return redirect(url_for("admin.client", slug=slug, tab="money"))


# ---------------------------------------------------------------- users, add-on, site key, portal

@admin_bp.route("/clients/<slug>/users", methods=["POST"])
def user_invite(slug):
    from routes.auth import send_invite
    a = _acct(slug)
    email = (request.form.get("email") or "").strip().lower()
    name = (request.form.get("name") or "").strip() or None
    if "@" not in email:
        flash("Enter a valid email address.", "err")
        return redirect(url_for("admin.client", slug=slug, tab="users"))
    u = User.query.filter(db.func.lower(User.email) == email).first()
    if u and u.is_admin:
        flash("That's an admin login. Use a different email for the client.", "err")
        return redirect(url_for("admin.client", slug=slug, tab="users"))
    if u and u.account_id not in (None, a.id):
        flash("That email already belongs to another client.", "err")
        return redirect(url_for("admin.client", slug=slug, tab="users"))
    if u is None:
        u = User(email=email, username=email, name=name, role="owner", account_id=a.id)
        db.session.add(u)
    u.account_id, u.is_active_flag = a.id, True
    u.name = name or u.name
    db.session.commit()
    try:
        send_invite(u)
        flash(f"Invite sent to {email}.", "ok")
    except Exception as exc:
        flash(f"User saved, but the email failed to send: {exc}", "err")
    return redirect(url_for("admin.client", slug=slug, tab="users"))


@admin_bp.route("/clients/<slug>/users/<int:uid>", methods=["POST"])
def user_update(slug, uid):
    from routes.auth import send_invite
    a = _acct(slug)
    u = User.query.filter_by(id=uid, account_id=a.id).first_or_404()
    action = request.form.get("action")
    if action == "disable":
        u.is_active_flag = False
        flash(f"{u.email} can no longer log in.", "ok")
    elif action == "enable":
        u.is_active_flag = True
        flash(f"{u.email} can log in again.", "ok")
    elif action == "resend":
        try:
            send_invite(u)
            flash(f"New invite link sent to {u.email}.", "ok")
        except Exception as exc:
            flash(f"Email failed: {exc}", "err")
    db.session.commit()
    return redirect(url_for("admin.client", slug=slug, tab="users"))


@admin_bp.route("/clients/<slug>/addon", methods=["POST"])
def addon_set(slug):
    a = _acct(slug)
    ad = a.addon() or AddOn(account_id=a.id, kind="reviews_updates")
    status = request.form.get("status")
    if status == "trial":
        days = max(1, min(90, int(request.form.get("days") or 30)))
        ad.status, ad.trial_ends_at = "trial", dt.date.today() + dt.timedelta(days=days)
    elif status in ("active", "paused"):
        ad.status = status
    if ad.id is None:
        db.session.add(ad)
    db.session.commit()
    flash(f"Reviews & Updates: {ad.status}{' until ' + ad.trial_ends_at.strftime('%-d %b') if ad.status == 'trial' else ''}.", "ok")
    return redirect(url_for("admin.client", slug=slug))


@admin_bp.route("/clients/<slug>/site-key", methods=["POST"])
def site_key(slug):
    a = _acct(slug)
    key = "ht_" + secrets.token_urlsafe(32)
    a.site_api_key_hash = generate_password_hash(key)
    db.session.commit()
    session["new_site_key"], session["new_site_key_for"] = key, a.slug     # shown once
    flash("New site key created. Copy it now: it won't be shown again. The old key has stopped working.", "ok")
    return redirect(url_for("admin.client", slug=slug, tab="site"))


@admin_bp.route("/clients/<slug>/portal")
def view_portal(slug):
    a = _acct(slug)
    session["portal_as"] = a.slug
    nxt = safe_next(request.args.get("next"))
    if nxt and nxt.startswith("/portal/"):
        return redirect(nxt)
    return redirect(url_for("portal.home", **{"as": a.slug}))


@admin_bp.route("/work")
def work():
    """Every client's jobs in one list (enquiries, bookings, unpaid invoices)."""
    from models.work import Invoice, Lead
    show = request.args.get("show", "open")
    q = Lead.query.filter(Lead.archived_at.is_(None))
    if show == "open":
        q = q.filter(Lead.status.in_(["new", "quoted", "accepted", "booked"]))
    elif show == "new":
        q = q.filter(Lead.status == "new")
    elif show == "done":
        q = q.filter(Lead.status == "done")
    rows = q.order_by(Lead.created_at.desc()).limit(300).all()
    unpaid = Invoice.query.filter(Invoice.status == "sent").order_by(Invoice.sent_at).all()
    return render_template("admin/work.html", rows=rows, show=show, unpaid=unpaid)


# ---------------------------------------------------------------- change requests (all clients)

@admin_bp.route("/requests")
def change_requests():
    rows = ChangeRequest.query.order_by(db.case((ChangeRequest.status == "done", 1), else_=0),
                                        ChangeRequest.created_at.desc()).all()
    return render_template("admin/change_requests.html", rows=rows)


@admin_bp.route("/requests/<int:rid>", methods=["POST"])
def change_request_set(rid):
    r = db.session.get(ChangeRequest, rid) or abort(404)
    if request.form.get("status") in ("new", "doing", "done"):
        r.status = request.form["status"]
        db.session.commit()
    return redirect(url_for("admin.change_requests"))


# ---------------------------------------------------------------- update notes for clients (docs/client-updates.md)

@admin_bp.route("/updates", methods=["GET", "POST"])
def updates():
    from utils import updates as upd
    secs = upd.sections()
    clients = Account.query.filter(Account.kind == "client", Account.status != "archived").order_by(Account.name).all()
    if request.method == "POST":
        try:
            sec = secs[int(request.form.get("section", -1))]
        except (ValueError, IndexError):
            abort(400)
        a = Account.query.filter_by(slug=request.form.get("client")).first_or_404()
        test = request.form.get("action") == "test"
        if not test and not a.contact_email:
            flash(f"{a.name} has no contact email.", "err")
            return redirect(url_for("admin.updates"))
        try:
            upd.send(a, sec, to=current_user.email if test else None)
        except Exception as exc:
            flash(f"Email failed: {exc}", "err")
            return redirect(url_for("admin.updates"))
        if test:
            flash(f"Test copy of {a.name}'s version sent to {current_user.email}.", "ok")
        else:
            db.session.add(Note(account_id=a.id, author_id=current_user.id, body=f"Update emailed: {sec['title']}"))
            db.session.commit()
            flash(f"Sent to {a.name} ({a.contact_email}).", "ok")
        return redirect(url_for("admin.updates"))
    sent = {}
    for n in Note.query.filter(Note.body.like("Update emailed: %")).all():
        sent.setdefault((n.account_id, n.body[len("Update emailed: "):]), n.created_at)
    previews = [[(a, upd.render(a, s)[1]) for a in clients] for s in secs]
    return render_template("admin/updates.html", secs=secs, clients=clients, previews=previews, sent=sent)
