# routes/portal_work.py — the client's jobs: enquiries, quotes, bookings, invoices, calendar, settings.
# Registered on the portal blueprint (imported at the bottom of routes/portal.py).
import datetime as dt
import json
import secrets
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.core import User
from models.reviews import ReviewRequest
from models.work import LEAD_STATUSES, Invoice, Lead, Quote, RepeatReminder, next_number
from utils import client_mail
from utils.links import public_url
from utils.security import owner_required, scoped

from .portal import addon_required, portal_bp

FILTERS = [("active", "Open"), ("new", "New"), ("quoted", "Quoted"), ("booked", "Booked"), ("done", "Done"),
           ("archive", "Archive")]


def owner_only(fn):
    """Money, website and staff settings: owners (and HapiTech admin) only, not staff."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_owner:
            flash("Only the business owner can do that.", "err")
            return redirect(url_for("portal.home"))
        return fn(*a, **kw)
    return wrapper


def _lead(lid) -> Lead:
    return scoped(Lead, id=lid).first_or_404()


def _dt(date_s, time_s):
    try:
        d = dt.date.fromisoformat(date_s)
    except (TypeError, ValueError):
        return None
    try:
        t = dt.time.fromisoformat(time_s) if time_s else dt.time(9, 0)
    except ValueError:
        t = dt.time(9, 0)
    return dt.datetime.combine(d, t)


def _items_from_form(form):
    descs, qtys, prices = form.getlist("desc"), form.getlist("qty"), form.getlist("price")
    items = []
    for d, q, p in zip(descs, qtys, prices):
        d = (d or "").strip()[:200]
        if not d:
            continue
        try:
            q = float(q or 1)
            p = float(Decimal(str(p or "0").replace("£", "").replace(",", "")))
        except (ValueError, InvalidOperation):
            raise ValueError(f"Check the numbers on “{d}”.")
        items.append({"desc": d, "qty": round(q, 2), "price": round(p, 2)})
    if not items:
        raise ValueError("Add at least one line.")
    return json.dumps(items)


# ---------------------------------------------------------------- list + create

@portal_bp.route("/jobs")
@owner_required
@addon_required
def jobs():
    show = request.args.get("show", "active")
    q = scoped(Lead).filter(Lead.status != "spam")
    if show == "archive":
        q = q.filter(Lead.archived_at.isnot(None))
    else:
        q = q.filter(Lead.archived_at.is_(None))
        if show == "active":
            q = q.filter(Lead.status.in_(["new", "quoted", "accepted", "booked"]))
        elif show in dict(LEAD_STATUSES):
            q = q.filter(Lead.status == show)
    rows = q.order_by(db.case((Lead.status == "new", 0), else_=1), Lead.start_at.is_(None),
                      Lead.start_at, Lead.created_at.desc()).all()
    counts = dict(db.session.query(Lead.status, db.func.count()).filter(
        Lead.account_id == g.account.id, Lead.archived_at.is_(None), Lead.status != "spam").group_by(Lead.status).all())
    return render_template("portal/jobs.html", rows=rows, show=show, filters=FILTERS, counts=counts)


@portal_bp.route("/jobs/new", methods=["GET", "POST"])
@owner_required
@addon_required
def job_new():
    if request.method == "POST":
        f = request.form
        name = (f.get("name") or "").strip()
        if not name:
            flash("Add the customer's name.", "err")
            return render_template("portal/job_form.html", lead=None, f=f)
        lead = Lead(account_id=g.account.id, source=f.get("source") if f.get("source") in ("phone", "manual") else "manual",
                    name=name[:120], email=(f.get("email") or "").strip()[:255] or None,
                    phone=(f.get("phone") or "").strip()[:40] or None,
                    postcode=(f.get("postcode") or "").strip().upper()[:12] or None,
                    address=(f.get("address") or "").strip()[:500] or None,
                    title=(f.get("title") or "").strip()[:160] or None, message=(f.get("message") or "").strip()[:5000] or None)
        db.session.add(lead)
        db.session.commit()
        flash("Job added.", "ok")
        return redirect(url_for("portal.job", lid=lead.id))
    return render_template("portal/job_form.html", lead=None, f={})


# ---------------------------------------------------------------- one job

@portal_bp.route("/jobs/<int:lid>", methods=["GET", "POST"])
@owner_required
@addon_required
def job(lid):
    lead = _lead(lid)
    if request.method == "POST":
        f, action = request.form, request.form.get("action")
        now = dt.datetime.utcnow()
        if action == "save":
            for k, n in (("name", 120), ("email", 255), ("phone", 40), ("postcode", 12), ("title", 160)):
                v = (f.get(k) or "").strip()[:n]
                setattr(lead, k, (v.upper() if k == "postcode" else v) or (lead.name if k == "name" else None))
            lead.address = (f.get("address") or "").strip()[:500] or None
            lead.notes = (f.get("notes") or "").strip()[:5000] or None
            flash("Saved.", "ok")
        elif action == "book":
            start = _dt(f.get("date"), f.get("time"))
            if not start:
                flash("Pick a date.", "err")
                return redirect(url_for("portal.job", lid=lid) + "#book")
            changed = lead.start_at != start
            lead.start_at, lead.days = start, max(1, min(60, int(f.get("days") or 1)))
            lead.status = "booked"
            if changed:
                lead.reminder_sent_at = None
            msg = f"Booked for {start.strftime('%a %-d %b, %-I:%M%p').lower().replace(':00', '')}."
            if f.get("notify") and lead.email:
                try:
                    client_mail.send_booking_confirmation(lead)
                    lead.confirm_sent_at = now
                    msg += f" Confirmation emailed to {lead.email}."
                except Exception as exc:
                    msg += f" (Email failed: {exc})"
            flash(msg, "ok")
        elif action == "done":
            lead.status, lead.done_at = "done", now
            msg = "Marked as done."
            if f.get("ask_review") and lead.email and g.account.has_addon():
                req = ReviewRequest(account_id=g.account.id, customer_name=lead.name.split()[0], job_ref=lead.title,
                                    sent_via="email", created_by=current_user.id)
                db.session.add(req)
                db.session.flush()
                try:
                    client_mail.send_review_request(lead, public_url(url_for("reviews_public.leave", token=req.token)))
                    lead.review_requested_at = now
                    msg += " Review request emailed."
                except Exception as exc:
                    msg += f" (Review email failed: {exc})"
            flash(msg, "ok")
        elif action == "make-client" and current_user.is_admin and g.account.kind == "internal" and not lead.for_account_id:
            from models.core import Account as _Acc, Note as _Note, User as _User, slugify as _slugify
            from routes.admin.clients import ADDED_NOTE
            email = (lead.email or "").strip().lower()
            if not email or _User.query.filter(db.func.lower(_User.email) == email).first():
                flash("They need an email address that doesn't already have a login.", "err")
                return redirect(url_for("portal.job", lid=lead.id))
            business = ""
            for line in (lead.notes or "").splitlines() + (lead.message or "").splitlines():
                if line.startswith("Business: "):
                    business = line[len("Business: "):].strip()
                    break
            name = business or lead.name
            base, n, slug = _slugify(name), 2, _slugify(name)
            while _Acc.query.filter_by(slug=slug).first():
                slug, n = f"{base}-{n}", n + 1
            acc = _Acc(kind="client", name=name[:160], slug=slug, contact_name=lead.name, contact_email=email,
                          contact_phone=lead.phone)
            db.session.add(acc)
            db.session.flush()
            db.session.add(_User(email=email, username=email, name=lead.name, role="owner", account_id=acc.id, is_active_flag=False))
            db.session.add(_Note(account_id=acc.id, author_id=current_user.id, body=ADDED_NOTE))
            db.session.add(_Note(account_id=acc.id, author_id=current_user.id, body=f"From enquiry: {lead.title or ''}\n\n{lead.message or ''}"[:4000]))
            lead.for_account_id = acc.id
            db.session.commit()
            flash(f"{acc.name} is now a client (login off). Send their invite from Emails to clients → Invite new clients.", "ok")
            return redirect(url_for("admin.client", slug=acc.slug))
        elif action == "spam" and lead.status == "new":
            db.session.delete(lead)
            db.session.commit()
            flash("Deleted as spam.", "ok")
            return redirect(url_for("portal.jobs"))
        elif action == "decline":
            lead.status, lead.declined_at = "declined", now
            flash("Marked as not going ahead. It'll be deleted automatically in 30 days.", "ok")
        elif action == "reopen":
            lead.status, lead.declined_at = "new", None
            flash("Reopened.", "ok")
        elif action == "archive":
            lead.archived_at = now
            flash("Archived.", "ok")
        elif action == "unarchive":
            lead.archived_at = None
            flash("Back in your jobs.", "ok")
        elif action == "delete":
            if not lead.can_delete:
                flash("Accepted jobs are kept. Archive it first, then delete it from the archive.", "err")
            else:
                db.session.delete(lead)
                db.session.commit()
                flash("Deleted, along with the customer's details.", "ok")
                return redirect(url_for("portal.jobs"))
        elif action == "remind":
            try:
                when = dt.date.fromisoformat(f.get("remind_on") or "")
            except ValueError:
                when = None
            note = (f.get("note") or "").strip()[:200]
            if not (when and note and f.get("consent") and lead.email):
                flash("Add a date, what to remind them about, an email, and tick that they asked for it.", "err")
            else:
                db.session.add(RepeatReminder(account_id=g.account.id, lead_id=lead.id, remind_on=when, note=note))
                flash(f"We'll email {lead.name.split()[0]} on {when.strftime('%-d %B %Y')}.", "ok")
        elif action == "cancel-reminder":
            rem = RepeatReminder.query.filter_by(id=int(f.get("rid") or 0), lead_id=lead.id).first()
            if rem:
                rem.cancelled_at = now
        db.session.commit()
        return redirect(url_for("portal.job", lid=lid))
    staff = User.query.filter_by(account_id=g.account.id, is_active_flag=True).all()
    return render_template("portal/job.html", lead=lead, staff=staff, today=dt.date.today())


# ---------------------------------------------------------------- quotes & invoices

def _priced_form(kind, lead, doc):
    title = "Quote" if kind == "quote" else "Invoice"
    return render_template("portal/priced_form.html", kind=kind, title=title, lead=lead, doc=doc,
                           vat_default=20 if g.account.vat_number else 0)


@portal_bp.route("/jobs/<int:lid>/<kind>", methods=["GET", "POST"])
@portal_bp.route("/jobs/<int:lid>/<kind>/<int:did>", methods=["GET", "POST"])
@owner_required
@addon_required
@owner_only
def priced(lid, kind, did=None):
    if kind not in ("quote", "invoice"):
        abort(404)
    lead = _lead(lid)
    Model, prefix = (Quote, "Q") if kind == "quote" else (Invoice, "INV")
    doc = Model.query.filter_by(id=did, lead_id=lead.id).first_or_404() if did else None
    if request.method == "GET" and doc is None and kind == "invoice" and lead.quotes:
        base = next((q for q in lead.quotes if q.status == "accepted"), lead.quotes[0])   # start from the quote
        doc = Invoice(items=base.items, vat_rate=base.vat_rate)
    if request.method == "POST":
        f = request.form
        if doc is None or doc.id is None:
            doc = Model(account_id=g.account.id, lead_id=lead.id, number=next_number(Model, g.account.id, prefix))
            db.session.add(doc)
        if f.get("action") == "paid" and kind == "invoice":
            doc.status, doc.paid_at = "paid", dt.datetime.utcnow()
            db.session.commit()
            flash(f"{doc.number} marked as paid.", "ok")
            return redirect(url_for("portal.job", lid=lid))
        if f.get("action") == "delete" and doc.status == "draft":
            db.session.delete(doc)
            db.session.commit()
            flash("Draft deleted.", "ok")
            return redirect(url_for("portal.job", lid=lid))
        try:
            doc.items = _items_from_form(f)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "err")
            return _priced_form(kind, lead, doc)
        try:
            doc.vat_rate = Decimal(str(f.get("vat_rate") or "0"))
        except InvalidOperation:
            doc.vat_rate = Decimal("0")
        doc.notes = (f.get("notes") or "").strip()[:3000] or None
        date_field = "valid_until" if kind == "quote" else "due_date"
        try:
            setattr(doc, date_field, dt.date.fromisoformat(f.get(date_field)) if f.get(date_field) else None)
        except ValueError:
            pass
        if f.get("action") == "send":
            if not lead.email:
                db.session.commit()
                flash("Add the customer's email to the job first, then send.", "err")
                return redirect(url_for("portal.priced", lid=lid, kind=kind, did=doc.id))
            try:
                db.session.flush()
                (client_mail.send_quote if kind == "quote" else client_mail.send_invoice)(doc)
                doc.status, doc.sent_at = ("sent" if doc.status != "paid" else "paid"), dt.datetime.utcnow()
                if kind == "quote" and lead.status == "new":
                    lead.status = "quoted"
                flash(f"{doc.number} emailed to {lead.email}.", "ok")
            except Exception as exc:
                flash(f"Saved, but the email failed: {exc}", "err")
        else:
            flash(f"{doc.number} saved.", "ok")
        db.session.commit()
        return redirect(url_for("portal.job", lid=lid))
    return _priced_form(kind, lead, doc)


# ---------------------------------------------------------------- calendar

@portal_bp.route("/calendar")
@owner_required
@addon_required
def calendar():
    a = g.account
    if not a.calendar_token:
        a.calendar_token = secrets.token_urlsafe(24)
        db.session.commit()
    today = dt.datetime.combine(dt.date.today(), dt.time())
    rows = (scoped(Lead).filter(Lead.status == "booked", Lead.archived_at.is_(None), Lead.start_at >= today - dt.timedelta(days=60))
            .order_by(Lead.start_at).all())
    upcoming = [r for r in rows if r.end_at >= today]
    days = {}
    for r in upcoming:
        days.setdefault(r.start_at.date(), []).append(r)
    feed = public_url(url_for("customer.calendar_feed", token=a.calendar_token))
    return render_template("portal/calendar.html", days=days, feed=feed, today=dt.date.today())


@portal_bp.route("/calendar/reset", methods=["POST"])
@owner_required
@owner_only
def calendar_reset():
    g.account.calendar_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash("New calendar link made. The old one has stopped working, so re-add it on your phone.", "ok")
    return redirect(url_for("portal.calendar"))


# ---------------------------------------------------------------- settings: business details, away, staff

@portal_bp.route("/settings", methods=["GET", "POST"])
@owner_required
@owner_only
def settings():
    a = g.account
    if request.method == "POST":
        f, action = request.form, request.form.get("action")
        if action == "business":
            a.business_address = (f.get("business_address") or "").strip()[:500] or None
            a.vat_number = (f.get("vat_number") or "").strip()[:40] or None
            a.payment_details = (f.get("payment_details") or "").strip()[:500] or None
            a.quote_terms = (f.get("quote_terms") or "").strip()[:2000] or None
            a.contact_email = (f.get("contact_email") or "").strip()[:255] or a.contact_email
            flash("Saved. These show on your quotes and invoices.", "ok")
        elif action == "away":
            try:
                a.away_until = dt.date.fromisoformat(f.get("away_until")) if f.get("away_until") else None
            except ValueError:
                a.away_until = None
            a.away_message = (f.get("away_message") or "").strip()[:200] or None
            flash(f"Away until {a.away_until.strftime('%-d %B')}. Your website shows this within 10 minutes."
                  if a.away_until else "You're back: the away notice is off.", "ok")
        elif action == "back":
            a.away_until = None
            flash("You're back: the away notice is off.", "ok")
        elif action == "invite":
            from routes.auth import send_invite
            email = (f.get("email") or "").strip().lower()
            if "@" not in email:
                flash("Enter their email address.", "err")
            elif User.query.filter(db.func.lower(User.email) == email).first():
                flash("That email already has a login.", "err")
            else:
                u = User(email=email, username=email, name=(f.get("name") or "").strip() or None, role="staff",
                         account_id=a.id)
                db.session.add(u)
                db.session.commit()
                try:
                    send_invite(u, inviter=current_user.name or a.name)
                    flash(f"{email} can now log in with an emailed code.", "ok")
                except Exception as exc:
                    flash(f"Added, but the email failed: {exc}", "err")
        elif action == "remove-staff":
            u = User.query.filter_by(id=int(f.get("uid") or 0), account_id=a.id, role="staff").first()
            if u:
                u.is_active_flag = False
                flash(f"{u.email} can no longer log in.", "ok")
        db.session.commit()
        return redirect(url_for("portal.settings"))
    staff = User.query.filter_by(account_id=a.id).order_by(User.role, User.email).all()
    return render_template("portal/settings.html", staff=staff, today=dt.date.today())


# ---------------------------------------------------------------- top-of-page (hero) photo

@portal_bp.route("/website/hero", methods=["GET", "POST"])
@owner_required
@addon_required
@owner_only
def hero():
    from utils.photos import HERO_MODES, hero_mode, hero_pick, known_photos, likes_map, photo_src, save_hero
    a = g.account
    if request.method == "POST":
        mode = request.form.get("mode", "all")
        pick = request.form.getlist("pick")
        if mode == "chosen" and not pick:
            flash("Tick at least one photo, or choose another option.", "err")
            return redirect(url_for("portal.hero"))
        save_hero(a, mode, pick, current_user.id)
        flash("Saved. Your website uses this within 10 minutes.", "ok")
        return redirect(url_for("portal.hero"))
    likes = likes_map(a)
    photos = [{"key": k, "src": photo_src(a, k), "likes": likes.get(k, 0)} for k in known_photos(a)]
    photos.sort(key=lambda p: -p["likes"])
    return render_template("portal/hero.html", modes=HERO_MODES, mode=hero_mode(a), pick=set(hero_pick(a)),
                           photos=photos, any_likes=bool(likes))


# ---------------------------------------------------------------- visitors

@portal_bp.route("/visitors")
@owner_required
@addon_required
def traffic():
    from utils.traffic import summary
    return render_template("portal/traffic.html", t=summary(g.account))



# ---------------------------------------------------------------- finances (with HapiTech)

@portal_bp.route("/finances")
def finances_old():
    return redirect(url_for("portal.plan"), code=301)


@portal_bp.route("/plan")
@owner_required
def plan():
    from decimal import Decimal

    from utils.plan_value import summary, support_options
    a = g.account
    ad = a.addon()
    friends = bool(ad and ad.status == "friends")
    support = support_options() if friends else []      # a small "Support HapiTech" button, Friends plan only
    from utils import work_requests as wr
    return render_template("portal/plan.html", owed=Decimal(a.balance_gbp or 0), addon=ad, v=summary(a), support=support,
                           work=wr.for_client(a), work_kinds=wr.KINDS, work_status=wr.CLIENT_STATUS)


@portal_bp.route("/support", methods=["POST"])
@owner_required
def support_pick():
    """A client chose a way to support HapiTech: note it on their account and tell Aaron.
    (We can't see whether the payment went through, only what they picked.)"""
    from flask import jsonify

    from models.core import Note
    d = request.get_json(silent=True) or {}
    method = {"paypal": "PayPal", "revolut": "Revolut"}.get(d.get("method"), "")
    if not method:
        return jsonify({"ok": False}), 400
    try:
        amount = f"£{int(d['amount'])}" if str(d.get("amount") or "").isdigit() else "an amount of their choice"
    except (KeyError, ValueError):
        amount = "an amount of their choice"
    who = current_user.name or current_user.email
    if not current_user.is_admin:
        db.session.add(Note(account_id=g.account.id, author_id=current_user.id,
                            body=f"Support HapiTech: chose {method} ({amount})"))
        db.session.commit()
        try:
            from utils import email_html
            email_html.send("aaron@hapitech.dev", f"{g.account.name} chose to support HapiTech ☕",
                            heading="Someone wants to support HapiTech ☕",
                            lines=[f"{who} ({g.account.name}) tapped Support HapiTech on their My plan page.",
                                   f"They chose {method}, {amount}. Check {method} to see if it came through, and say thanks!"],
                            box=[("Business", g.account.name), ("Chose", f"{method} · {amount}"), ("Their email", current_user.email)],
                            reply_to=current_user.email)
        except Exception as exc:
            print(f"[SUPPORT_NOTIFY] {exc}")
    return jsonify({"ok": True})


@portal_bp.route("/plan/<ref>")
@owner_required
def receipt(ref):
    from utils.plan_value import find
    t = find(g.account, ref)
    if not t:
        abort(404)
    return render_template("portal/receipt.html", t=t, a=g.account, addon=g.account.addon())



# ---------------------------------------------------------------- asking HapiTech for extra work

@portal_bp.route("/requests/work", methods=["POST"])
@owner_required
def work_request():
    from utils import work_requests as wr
    f = request.form
    what = (f.get("what") or "").strip()[:4000]
    back = f.get("back") if f.get("back") in ("plan", "website") else "plan"
    if not what:
        flash("Tell Aaron what you'd like done.", "err")
    else:
        offer = wr.parse_offer(f.get("offer"))
        if (f.get("offer") or "").strip() and offer is None:
            flash("That amount didn't look right, so it was sent without one. Aaron will quote you.", "err")
        if current_user.is_admin and g.account.kind != "internal":
            flash("(Viewing as admin: not sent.)", "ok")
        else:
            wr.create(g.account, current_user, f.get("kind"), what, offer)
            flash("Sent to Aaron. " + ("He'll confirm it with you." if offer else "He'll reply with a quote."), "ok")
    return redirect(url_for("portal.website" if back == "website" else "portal.plan") + "#work")
