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
    # unpaid work, per client: finished work vs every payment that isn't for a subscription
    # (one payment often covers several stages of the same order, so jobs aren't checked one by one)
    unpaid_jobs = []
    for acc in Account.query.filter(Account.kind == "client").all():
        work = sum(float(j.price_gbp or 0) for j in acc.jobs if j.status == "done")
        paid = sum(float(p.amount_gbp or 0) for p in acc.payments if not p.subscription_id)
        if work - paid > 0.005:
            unpaid_jobs.append({"account": acc, "owed": round(work - paid, 2)})
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
    q = Account.query.filter(Account.kind.in_(["client", "internal"]))
    q = q.filter(Account.status == "archived") if show == "archived" else q.filter(Account.status != "archived")
    rows = []
    for a in q.order_by(Account.name).all():
        rows.append({
            "a": a,
            "mrr": sum(s.monthly_gbp for s in a.subscriptions if s.status == "active"),
            "paid": sum(float(p.amount_gbp or 0) for p in a.payments),
            "reviews": Review.query.filter_by(account_id=a.id, status="published").count(),
            "open_jobs": sum(1 for j in a.jobs if j.status in ("quote", "booked", "in_progress")),
            "seen": max([t for u in a.users for t in (u.last_seen_at, u.last_login_at) if t], default=None),
        })
    rows.sort(key=lambda r: (r["a"].kind == "internal", r["a"].name.lower()))      # our own sites last
    return render_template("admin/clients.html", rows=rows, show=show)


ACCOUNT_FIELDS = ("name", "domain", "trade", "town", "contact_name", "contact_email", "contact_phone",
                  "google_profile_url", "google_reviews_url", "google_maps_url", "facebook_url", "logo_path", "brand_colour", "notes", "status")


def _fill_account(a: Account, form):
    for f in ACCOUNT_FIELDS:
        if f in form:
            setattr(a, f, (form.get(f) or "").strip() or None)
    if "balance_gbp" in form:
        try:
            a.balance_gbp = _money(form.get("balance_gbp")) or None
        except Exception:
            pass
    if "features_sent" in form:
        import json as _json
        from utils.features import ALL
        picked = [f for f in ALL if f in form.getlist("features")]
        a.features = None if not picked or len(picked) == len(ALL) else _json.dumps(picked)
    if "shortcuts_text" in form:
        import json as _json
        rows = []
        for line in (form.get("shortcuts_text") or "").splitlines():
            if "|" in line:
                label, url = [x.strip() for x in line.split("|", 1)]
                if label and url.startswith("https://"):
                    rows.append([label[:40], url[:300]])
        a.shortcuts = _json.dumps(rows) if rows else None
    if "billing_note" in form:
        a.billing_note = (form.get("billing_note") or "").strip()[:1000] or None
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
        return redirect(url_for("admin.client", slug=a.slug, tab=request.form.get("back") or None))
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
    value = None
    if tab == "money":
        from utils.plan_value import summary
        value = summary(a)
    traffic = None
    if tab == "traffic":
        from utils.traffic import summary
        traffic = summary(a)
    return render_template("admin/client.html", a=a, tab=tab, reviews=reviews, stats=stats,
                           job_types=JOB_TYPES, job_statuses=JOB_STATUSES, today=dt.date.today(), new_key=new_key,
                           t=traffic, value=value, extras=__import__("utils.extras", fromlist=["x"]).EXTRAS,
                           extra_status=__import__("utils.extras", fromlist=["x"]).status, friends_end=__import__("utils.plans", fromlist=["x"]).friends_end_default())


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


@admin_bp.route("/clients/<slug>/costs", methods=["POST"])
@admin_bp.route("/clients/<slug>/costs/<int:cid>", methods=["POST"])
def cost_save(slug, cid=None):
    from models.core import RunningCost
    a = _acct(slug)
    c = RunningCost.query.filter_by(id=cid, account_id=a.id).first_or_404() if cid else RunningCost(account_id=a.id)
    f = request.form
    if f.get("action") == "delete" and cid:
        db.session.delete(c)
        db.session.commit()
        flash("Running cost removed.", "ok")
        return redirect(url_for("admin.client", slug=slug, tab="money") + "#costs")
    c.title = (f.get("title") or "").strip()[:160] or "Running cost"
    c.kind = f.get("kind") if f.get("kind") in ("hosting", "email", "domain", "other") else "other"
    c.value_gbp = _money(f.get("value_gbp"))
    c.my_cost_gbp = _money(f.get("my_cost_gbp")) if (f.get("my_cost_gbp") or "").strip() else None
    c.interval = f.get("interval") if f.get("interval") in ("monthly", "quarterly", "yearly", "once") else "monthly"
    c.started_on, c.ended_on = _date(f.get("started_on")), _date(f.get("ended_on"))
    c.covered = bool(f.get("covered"))
    c.note = (f.get("note") or "").strip()[:300] or None
    if not cid:
        db.session.add(c)
    db.session.commit()
    flash("Running cost saved.", "ok")
    return redirect(url_for("admin.client", slug=slug, tab="money") + "#costs")


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
    elif status == "friends":
        from utils.plans import RENEW_MONTHS, start_friends
        try:
            until = dt.date.fromisoformat(request.form.get("until") or "")
        except ValueError:
            until = None
        months = request.form.get("renew_months")
        start_friends(ad, until, int(months) if request.form.get("renew") and (months or "").isdigit() and int(months) > 0
                      else (RENEW_MONTHS if request.form.get("renew") else None))
    elif status in ("active", "paused"):
        ad.status = status
    if ad.id is None:
        db.session.add(ad)
    db.session.commit()
    flash(f"Dashboard plan: {ad.plan['name']}. {ad.plan['admin']}", "ok")
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
    elif show == "spam":
        q = q.filter(Lead.status == "spam")
    if show != "spam":
        q = q.filter(Lead.status != "spam")
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

ADDED_NOTE = "Added from Emails to clients, ready to invite"
GENERIC_NOTE = "Added for a dashboard invite (no website from us)"
GENERIC_FILE = "docs/dashboard-invite.md"


def _invite_mode():
    from models.core import SystemState
    row = db.session.get(SystemState, "invite_mode")
    return row.value if row and row.value in ("personal", "generic") else "personal"


@admin_bp.route("/updates", methods=["GET", "POST"])
def updates():
    """Emails to clients. Tabs: What's new (a mailing list: write a message, or send a note from
    docs/client-updates.md), Dashboard invite (docs/client-invite.md), Invite new clients."""
    from utils import updates as upd
    from utils.plans import start_friends
    invites, notes, generic = upd.sections(upd.INVITE_FILE), upd.sections(upd.FILE), upd.sections(GENERIC_FILE)
    mode = _invite_mode()
    clients = Account.query.filter(Account.kind == "client", Account.status != "archived").order_by(Account.name).all()
    added_ids = {n.account_id for n in Note.query.filter_by(body=ADDED_NOTE).all()}
    generic_ids = {n.account_id for n in Note.query.filter_by(body=GENERIC_NOTE).all()}
    show = request.values.get("show") or request.form.get("kind") or "update"
    if show not in ("update", "invite", "new", "message"):
        show = "update"
    compose, compose_previews = {}, []

    if request.method == "POST":
        kind = request.form.get("kind")
        action = request.form.get("action")
        if kind == "invite-mode":
            from models.core import SystemState
            row = db.session.get(SystemState, "invite_mode") or SystemState(key="invite_mode")
            row.value = "generic" if request.form.get("mode") == "generic" else "personal"
            db.session.add(row)
            db.session.commit()
            flash("Dashboard invite switched to the generic invite." if row.value == "generic" else "Back to Ray and Roland's invite.", "ok")
            return redirect(url_for("admin.updates", show="invite"))
        if kind == "message":
            # a one-off message written here, to the ticked clients
            subject = (request.form.get("subject") or "").strip()[:150]
            body = (request.form.get("body") or "").strip()[:8000]
            picked = [c for c in clients if c.slug in request.form.getlist("to")]
            compose = {"subject": subject, "body": body, "to": [c.slug for c in picked]}
            if not subject or not body:
                flash("Add a subject and a message.", "err")
            elif action == "preview" or not picked and action != "test":
                if not picked:
                    flash("Tick who it's for.", "err")
                compose_previews = [(c, upd.page(c, {"title": subject, "body": body})[1]) for c in (picked or clients[:1])]
            else:
                sec = {"title": subject, "body": body}
                targets = [(picked[0] if picked else clients[0], current_user.email)] if action == "test" else \
                          [(c, upd.owner_email(c)) for c in picked]
                sent, failed = [], []
                for c, to in targets:
                    if not to:
                        failed.append(f"{c.name} (no email)")
                        continue
                    try:
                        upd.send(c, sec, to=to)
                        sent.append(c.name)
                        if action != "test":
                            db.session.add(Note(account_id=c.id, author_id=current_user.id, body=f"Message emailed: {subject}"))
                    except Exception as exc:
                        failed.append(f"{c.name} ({exc})")
                db.session.commit()
                if action == "test":
                    flash(f"Test sent to {current_user.email}.", "ok") if sent else flash("Test failed: " + "; ".join(failed), "err")
                    compose_previews = [(targets[0][0], upd.page(targets[0][0], sec)[1])]
                else:
                    if sent:
                        flash(f"Sent to {', '.join(sent)}.", "ok")
                        compose = {}
                    if failed:
                        flash("Not sent: " + "; ".join(failed), "err")
            show = "update"
        else:
            a = Account.query.filter_by(slug=request.form.get("client")).first_or_404()
            if kind == "generic":
                secs = generic
                sec = secs[0 if a.has_feature("jobs") or len(secs) < 2 else 1] if secs else abort(400)
                label = "Invite emailed"
            else:
                secs, label = (invites, "Invite emailed") if kind == "invite" else (notes, "Update emailed")
                try:
                    sec = secs[int(request.form.get("section", -1))]
                except (ValueError, IndexError):
                    abort(400)
            back = request.form.get("back") or kind
            test = action == "test"
            to = current_user.email if test else upd.owner_email(a)
            if not to:
                flash(f"{a.name} has no owner login or contact email.", "err")
                return redirect(url_for("admin.updates", show=back))
            if kind == "generic" and not test:
                owner = User.query.filter_by(account_id=a.id, role="owner").order_by(User.id).first()
                if owner:
                    owner.is_active_flag = True
                db.session.commit()
            if kind == "invite" and not test:
                # switch on their login and the Friends plan (unless they're already on it)
                owner = User.query.filter_by(account_id=a.id, role="owner").order_by(User.id).first()
                if owner is None:
                    owner = User(email=to, username=to, name=a.contact_name, role="owner", account_id=a.id)
                    db.session.add(owner)
                owner.is_active_flag = True
                ad = a.addon() or AddOn(account_id=a.id, kind="reviews_updates")
                if ad.status != "friends":
                    start_friends(ad)
                if ad.id is None:
                    db.session.add(ad)
                db.session.commit()
            try:
                upd.send(a, sec, to=to)
            except Exception as exc:
                flash(f"Email failed: {exc}", "err")
                return redirect(url_for("admin.updates", show=back))
            if test:
                flash(f"Test copy of {a.name}'s email sent to {current_user.email}.", "ok")
            else:
                db.session.add(Note(account_id=a.id, author_id=current_user.id, body=f"{label}: {sec['title']}"))
                db.session.commit()
                flash(f"Sent to {a.name} ({to})." + (" Their login and Friends plan are switched on." if kind == "invite" else
                                                       " Their login is switched on." if kind == "generic" else ""), "ok")
            return redirect(url_for("admin.updates", show=back) + f"#c-{a.slug}")

    sent = {}
    for n in Note.query.filter(db.or_(Note.body.like("Update emailed: %"), Note.body.like("Invite emailed: %"))).all():
        sent.setdefault((n.account_id, n.body.split(": ", 1)[1]), n.created_at)
    history = (Note.query.filter(Note.body.like("Message emailed: %")).order_by(Note.created_at.desc()).limit(40).all()
               if show == "update" else [])
    if show == "update":
        secs, people = notes, clients
    elif show == "invite" and mode == "generic":
        people = [c for c in clients if c.id in generic_ids]
        full, rev = (generic + generic)[:2] if generic else (None, None)
        previews = [[(a, upd.page(a, full if a.has_feature("jobs") else rev)[1], upd.owner_email(a)) for a in people]] if generic else [[]]
        secs = [{"title": "Dashboard invite"}]
        return render_template("admin/updates.html", secs=secs, clients=clients, previews=previews, sent=_sent_any(people), show=show,
                               compose={}, compose_previews=[], history=[], kind="generic", mode=mode)
    elif show == "invite":
        secs, people = invites, [c for c in clients if c.id not in added_ids | generic_ids]
    else:
        secs, people = invites, [c for c in clients if c.id in added_ids]
    if show == "update":
        people = [c for c in people if c.id not in generic_ids]   # What's new is about their website
    previews = [[(a, upd.page(a, s)[1], upd.owner_email(a)) for a in people] for s in secs]
    return render_template("admin/updates.html", secs=secs, clients=clients, previews=previews, sent=sent, show=show,
                           compose=compose, compose_previews=compose_previews, history=history,
                           kind="update" if show == "update" else "invite", mode=mode)


def _sent_any(people):
    """Generic invites: {(account id, "Dashboard invite"): when} for anyone who's had an invite."""
    out = {}
    for n in Note.query.filter(Note.account_id.in_([p.id for p in people] or [-1]), Note.body.like("Invite emailed: %")).all():
        out.setdefault((n.account_id, "Dashboard invite"), n.created_at)
    return out


@admin_bp.route("/updates/generic", methods=["POST"])
def invite_generic():
    """Generic dashboard invite: someone we haven't built a website for, maybe only after reviews."""
    from utils.features import PRESETS
    from utils.plans import start_friends
    f = request.form
    name, who = (f.get("business") or "").strip()[:160], (f.get("contact_name") or "").strip()[:120]
    email = (f.get("email") or "").strip().lower()
    if not name or "@" not in email:
        flash("Add their business name and email.", "err")
        return redirect(url_for("admin.updates", show="invite"))
    if User.query.filter(db.func.lower(User.email) == email).first():
        flash("That email already has a login.", "err")
        return redirect(url_for("admin.updates", show="invite"))
    base, n, slug = slugify(name), 2, slugify(name)
    while Account.query.filter_by(slug=slug).first():
        slug, n = f"{base}-{n}", n + 1
    import json as _json
    preset = f.get("features") if f.get("features") in PRESETS else "reviews"
    a = Account(kind="client", name=name, slug=slug, contact_name=who or None, contact_email=email,
                trade=(f.get("trade") or "").strip()[:120] or None, town=(f.get("town") or "").strip()[:120] or None,
                features=None if preset == "all" else _json.dumps(PRESETS[preset]))
    db.session.add(a)
    db.session.flush()
    db.session.add(User(email=email, username=email, name=who or None, role="owner", account_id=a.id, is_active_flag=False))
    ad = AddOn(account_id=a.id, kind="reviews_updates")
    if f.get("friends"):
        start_friends(ad)
    db.session.add(ad)
    db.session.add(Note(account_id=a.id, author_id=current_user.id, body=GENERIC_NOTE))
    db.session.commit()
    flash(f"{name} added. Check their invite below, then send it.", "ok")
    return redirect(url_for("admin.updates", show="invite") + f"#c-{a.slug}")


@admin_bp.route("/updates/new", methods=["POST"])
def invite_new():
    """Add someone new as a client (login off until the invite is sent) so their invite can be previewed and sent."""
    f = request.form
    name, who = (f.get("business") or "").strip()[:160], (f.get("contact_name") or "").strip()[:120]
    email = (f.get("email") or "").strip().lower()
    if not name or "@" not in email:
        flash("Add their business name and email.", "err")
        return redirect(url_for("admin.updates", show="new"))
    if User.query.filter(db.func.lower(User.email) == email).first():
        flash("That email already has a login.", "err")
        return redirect(url_for("admin.updates", show="new"))
    base, n, slug = slugify(name), 2, slugify(name)
    while Account.query.filter_by(slug=slug).first():
        slug, n = f"{base}-{n}", n + 1
    domain = (f.get("domain") or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/") or None
    a = Account(kind="client", name=name, slug=slug, contact_name=who or None, contact_email=email, domain=domain)
    db.session.add(a)
    db.session.flush()
    db.session.add(User(email=email, username=email, name=who or None, role="owner", account_id=a.id, is_active_flag=False))
    db.session.add(Note(account_id=a.id, author_id=current_user.id, body=ADDED_NOTE))
    db.session.commit()
    flash(f"{name} added. Check their invite below, then send it.", "ok")
    return redirect(url_for("admin.updates", show="new") + f"#c-{a.slug}")


@admin_bp.route("/me/<what>")
def me(what):
    """HapiTech's own posts / reviews: open them in the same dashboard screens the clients use."""
    from utils.hapitech_account import get
    a = get()
    session["portal_as"] = a.slug
    target = {"post": "/portal/posts/new", "posts": "/portal/posts", "reviews": "/portal/reviews",
              "ask": "/portal/ask", "jobs": "/portal/jobs"}.get(what, "/portal/posts")
    return redirect(target)


@admin_bp.route("/clients/<slug>/extras/<key>", methods=["POST"])
def extra_set(slug, key):
    from utils.extras import EXTRAS
    a = _acct(slug)
    if key not in [x["key"] for x in EXTRAS]:
        abort(404)
    ad = a.addon(key)
    st = request.form.get("status")
    if st == "remove":
        if ad:
            db.session.delete(ad)
    elif st in ("active", "paused"):
        if ad is None:
            ad = AddOn(account_id=a.id, kind=key)
            db.session.add(ad)
        ad.status = st
    db.session.commit()
    flash("Extra updated.", "ok")
    return redirect(url_for("admin.client", slug=slug))
