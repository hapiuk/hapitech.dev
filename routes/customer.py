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
    """Tell the business owner something happened (in their own name and colours, with a button to their dashboard)."""
    to = account.contact_email or next((u.email for u in account.users if u.role == "owner" and u.is_active), None)
    if not to:
        return
    try:
        from flask import url_for

        from utils import email_html
        from utils.links import public_url
        email_html.send(to, subject, account=account, heading=heading, lines=lines, box=box,
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


def pay_for(inv):
    """The invoice's "Pay now" button, pointed at our own /i/<token>/pay step (so the business hears the link was
    opened) instead of straight at the provider. None when paid or there's no link."""
    from flask import url_for

    from utils.links import public_url
    from utils.pay_links import for_invoice
    if inv.status == "paid":
        return None
    pay = for_invoice(inv.lead.account, float(inv.totals[2]))
    if pay:
        pay["dest"], pay["url"] = pay["url"], public_url(url_for("customer.invoice_pay", token=inv.token))
    return pay


@customer_bp.route("/i/<token>")
def invoice(token):
    inv = Invoice.query.filter_by(token=token).first()
    if not inv or inv.status == "draft":
        abort(404)
    return render_template("customer/invoice.html", a=inv.lead.account, inv=inv, lead=inv.lead, pay=pay_for(inv))


PAY_ALERT_GAP = dt.timedelta(hours=6)          # at most one "pay link opened" email per invoice per 6 hours


@customer_bp.route("/i/<token>/pay", methods=["GET", "POST"])
def invoice_pay(token):
    """The customer pressed "Pay now". GET shows a moment's "taking you to Revolut" page whose script reports the
    click (POST) and then moves on, so email link-scanners that only fetch the page don't count as a click.
    This only tells the business the link was OPENED: it is not proof of payment."""
    inv = Invoice.query.filter_by(token=token).first()
    if not inv or inv.status == "draft":
        abort(404)
    a = inv.lead.account
    pay = pay_for(inv)
    if not pay:                                  # paid already, or the link was removed: show the invoice
        from flask import redirect, url_for
        return redirect(url_for("customer.invoice", token=token))
    if request.method == "POST":
        now = dt.datetime.utcnow()
        first_in_a_while = not inv.pay_clicked_at or now - inv.pay_clicked_at > PAY_ALERT_GAP
        inv.pay_clicked_at, inv.pay_clicks = now, (inv.pay_clicks or 0) + 1
        db.session.commit()
        if first_in_a_while:
            lead = inv.lead
            _notify_owner(a, f"{lead.name} opened the payment link for {inv.number}",
                          "Payment link opened",
                          [f"{lead.name} just opened the {pay['label']} payment link on invoice {inv.number}.",
                           "This only means they opened the link. It isn't confirmation that they've paid. "
                           "Check your account, then press Mark paid on the job when the money arrives."],
                          box=[("Invoice", inv.number), ("Amount", f"£{inv.totals[2]:,.2f}"),
                               ("Reference", inv.reference), ("Job", lead.label)])
        return ("", 204)
    return render_template("customer/pay_go.html", a=a, inv=inv, pay=pay)


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
    if a.slug == "hapitech":                      # Aaron's feed: task reminders as all-day events
        from models.tasks import Task
        for t in Task.query.filter(Task.status != "done", Task.remind_on.isnot(None)).all():
            lines += ["BEGIN:VEVENT", f"UID:task-{t.id}-{t.remind_on:%Y%m%d}@hapitech.dev", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{t.remind_on:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{(t.remind_on + dt.timedelta(days=1)):%Y%m%d}",
                      f"SUMMARY:{_ics_escape('⏰ ' + t.ref + ' ' + t.title)}",
                      f"DESCRIPTION:{_ics_escape(t.tag + chr(10) + 'https://hapitech.dev/admin/tasks/' + str(t.id))}",
                      "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(t.ref + ' ' + t.title)}",
                      "TRIGGER:PT9H", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    resp = make_response("\r\n".join(lines) + "\r\n")
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp
