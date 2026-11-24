# routes/customer.py — pages a client's customers (and phone calendars) open from links.
# Every link carries an unguessable token; nothing here needs a login.
import datetime as dt

from flask import Blueprint, abort, make_response, render_template, request

from models import db
from models.core import Account
from models.work import Invoice, Lead, Quote, RepeatReminder
from utils.mailer import send_email

customer_bp = Blueprint("customer", __name__)


def _notify_owner(account, subject, heading, lines, box=None):
    """Tell the business owner something happened (HapiTech-branded, with a button to their dashboard)."""
    if not account.contact_email:
        return
    try:
        from flask import url_for

        from utils import email_html
        from utils.links import public_url
        email_html.send(account.contact_email, subject, heading=heading, lines=lines, box=box,
                        button={"label": "Open your dashboard", "url": public_url(url_for("portal.jobs"))})
    except Exception as exc:
        print(f"[CUSTOMER_NOTIFY] {exc}")


@customer_bp.route("/q/<token>", methods=["GET", "POST"])
def quote(token):
    q = Quote.query.filter_by(token=token).first()
    if not q or q.status == "draft":
        abort(404)
    a, lead = q.lead.account, q.lead
    if request.method == "POST" and q.status == "sent":
        now = dt.datetime.utcnow()
        if request.form.get("answer") == "accept":
            q.status, q.responded_at = "accepted", now
            if lead.status in ("new", "quoted"):
                lead.status = "accepted"
            if a.kind == "internal":                 # HapiTech's own job: it becomes a task under the client
                from routes.portal_work import accept_into_task, client_for_lead
                db.session.commit()
                accept_into_task(lead, client_for_lead(lead), user_id=None)
            _notify_owner(a, f"Good news: {lead.name} accepted your quote",
                          "Your quote was accepted 🎉", [f"{lead.name} accepted your quote. Next, pick a date for the job."],
                          box=[("Quote", q.number), ("Total", f"£{q.totals[2]:,.2f}"), ("Job", lead.label)])
        elif request.form.get("answer") == "decline":
            q.status, q.responded_at = "declined", now
            _notify_owner(a, f"{lead.name} said no thanks to quote {q.number}", "Quote declined",
                          [f"{lead.name} decided not to go ahead with quote {q.number}."],
                          box=[("Job", lead.label)])
        db.session.commit()
    return render_template("customer/quote.html", a=a, q=q, lead=lead)


@customer_bp.route("/i/<token>")
def invoice(token):
    inv = Invoice.query.filter_by(token=token).first()
    if not inv or inv.status == "draft":
        abort(404)
    return render_template("customer/invoice.html", a=inv.lead.account, inv=inv, lead=inv.lead)


@customer_bp.route("/u/<token>", methods=["GET", "POST"])
def reminder_stop(token):
    rem = RepeatReminder.query.filter_by(token=token).first() or abort(404)
    if request.method == "POST" and not rem.cancelled_at:
        rem.cancelled_at = dt.datetime.utcnow()
        db.session.commit()
    return render_template("customer/reminder_stop.html", a=rem.lead.account, rem=rem)


def _ics_escape(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@customer_bp.route("/cal/<token>.ics")
def calendar_feed(token):
    """Read-only calendar feed of the client's bookings, for their phone's calendar app."""
    if not token or len(token) < 20:
        abort(404)
    a = Account.query.filter_by(calendar_token=token).first() or abort(404)
    since = dt.datetime.utcnow() - dt.timedelta(days=90)
    leads = Lead.query.filter(Lead.account_id == a.id, Lead.status.in_(["booked", "done"]), Lead.start_at >= since,
                              Lead.archived_at.is_(None)).all()
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HapiTech//Jobs//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_ics_escape(a.name)} jobs", "X-WR-TIMEZONE:Europe/London",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for l in leads:
        start = l.start_at
        if l.days > 1:      # multi-day job: all-day block
            dtstart = f"DTSTART;VALUE=DATE:{start:%Y%m%d}"
            dtend = f"DTEND;VALUE=DATE:{(start + dt.timedelta(days=l.days)):%Y%m%d}"
        else:
            dtstart = f"DTSTART;TZID=Europe/London:{start:%Y%m%dT%H%M%S}"
            dtend = f"DTEND;TZID=Europe/London:{(start + dt.timedelta(hours=2)):%Y%m%dT%H%M%S}"
        desc = "\n".join(x for x in [l.phone and f"Tel: {l.phone}", l.address, l.notes] if x)
        lines += ["BEGIN:VEVENT", f"UID:job-{l.id}@hapitech.dev", f"DTSTAMP:{stamp}", dtstart, dtend,
                  f"SUMMARY:{_ics_escape(l.label + ' – ' + l.name)}",
                  f"LOCATION:{_ics_escape(l.postcode or '')}", f"DESCRIPTION:{_ics_escape(desc)}",
                  "STATUS:CONFIRMED" if l.status == "booked" else "STATUS:CONFIRMED", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    resp = make_response("\r\n".join(lines) + "\r\n")
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp
