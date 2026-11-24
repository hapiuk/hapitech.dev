# utils/tasks.py — background jobs: booking reminders, repeat reminders, data retention.
#
# No cron needed: maybe_run() is called on incoming requests (client sites poll the API every
# ~10 minutes, so there's steady traffic) and runs the jobs at most every RUN_EVERY in a background
# thread. A lease row in system_state stops two gunicorn workers running them at the same time.
# `flask tick` runs them by hand.
import datetime as dt
import threading
import time

from sqlalchemy import text

RUN_EVERY = 300            # seconds
_last_check = 0.0
_guard = threading.Lock()


def _take_lease(db, seconds=240) -> bool:
    now = dt.datetime.utcnow()
    until = (now + dt.timedelta(seconds=seconds)).isoformat()
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO system_state (key, value, updated_at) VALUES ('tick_lease', '', :n) "
                          "ON CONFLICT (key) DO NOTHING"), {"n": now})
        res = conn.execute(text("UPDATE system_state SET value = :until, updated_at = :n "
                                "WHERE key = 'tick_lease' AND (value = '' OR value < :now)"),
                           {"until": until, "n": now, "now": now.isoformat()})
        return res.rowcount == 1


def run_all(app, force=False) -> dict:
    """Run every due job. Returns a summary (used by `flask tick` and tests)."""
    from models import db
    from models.work import DECLINED_RETENTION_DAYS, Lead, RepeatReminder
    from utils.client_mail import send_booking_reminder, send_repeat_reminder

    out = {"reminders": 0, "repeat": 0, "deleted": 0, "errors": 0}
    # a request context so emails can build absolute links (no real request in the background)
    base = app.config.get("PUBLIC_BASE_URL") or "http://127.0.0.1:5077"
    with app.app_context(), app.test_request_context("/", base_url=base):
        if not force and not _take_lease(db):
            return out
        now = dt.datetime.utcnow()
        tomorrow = (now + dt.timedelta(days=1)).date()

        # "see you tomorrow" emails, sent from 8am the day before
        if now.hour >= 8:
            due = Lead.query.filter(Lead.status == "booked", Lead.reminder_sent_at.is_(None),
                                    Lead.email.isnot(None), Lead.archived_at.is_(None),
                                    Lead.start_at >= dt.datetime.combine(tomorrow, dt.time()),
                                    Lead.start_at < dt.datetime.combine(tomorrow + dt.timedelta(days=1), dt.time())).all()
            for lead in due:
                try:
                    send_booking_reminder(lead)
                    lead.reminder_sent_at = now
                    out["reminders"] += 1
                except Exception as exc:
                    out["errors"] += 1
                    print(f"[TASK reminder {lead.id}] {exc}")
            db.session.commit()

        # opt-in repeat reminders ("remind me about the gutters next autumn")
        for rem in RepeatReminder.query.filter(RepeatReminder.remind_on <= now.date(), RepeatReminder.sent_at.is_(None),
                                               RepeatReminder.cancelled_at.is_(None)).all():
            try:
                send_repeat_reminder(rem)
                rem.sent_at = now
                out["repeat"] += 1
            except Exception as exc:
                out["errors"] += 1
                print(f"[TASK repeat {rem.id}] {exc}")
        db.session.commit()

        # the business's own reminder: "your jobs today", once a day from 7am (customers get theirs separately)
        if now.hour >= 7:
            try:
                out["jobs_today"] = send_jobs_today(now)
            except Exception as exc:
                out["errors"] += 1
                print(f"[TASK jobs-today] {exc}")

        # Aaron's task reminders: one email listing every task whose remind-on date has come (from 8am)
        if now.hour >= 8:
            try:
                out["task_reminders"] = send_task_reminders(now)
            except Exception as exc:
                out["errors"] += 1
                print(f"[TASK task-reminders] {exc}")

        # Friends plans set to auto-renew roll their end date on (every 3 months by default)
        from models.core import AddOn
        from utils.plans import roll_forward
        out["friends_renewed"] = sum(1 for ad in AddOn.query.filter_by(status="friends").all() if roll_forward(ad))
        db.session.commit()

        # fairness: open-form reviews nobody acted on go live after 14 days (unless marked spam)
        from models.reviews import Review
        from routes.reviews_public import PENDING_AUTO_PUBLISH_DAYS
        stale = now - dt.timedelta(days=PENDING_AUTO_PUBLISH_DAYS)
        out["auto_published"] = Review.query.filter(Review.status == "pending", Review.created_at < stale) \
            .update({"status": "published"}, synchronize_session=False)
        db.session.commit()

        # spam enquiries: kept 14 days (in case one was real), then deleted
        from models.work import Lead as _Lead
        out["spam_deleted"] = _Lead.query.filter(_Lead.status == "spam",
                                                 _Lead.created_at < now - dt.timedelta(days=14)).delete(synchronize_session=False)
        db.session.commit()

        # retention: declined jobs go after 30 days (accepted/done ones are never auto-deleted)
        cutoff = now - dt.timedelta(days=DECLINED_RETENTION_DAYS)
        for lead in Lead.query.filter(Lead.status == "declined", Lead.declined_at < cutoff).all():
            db.session.delete(lead)
            out["deleted"] += 1
        db.session.commit()
    return out


def maybe_run(app):
    global _last_check
    if app.config.get("TESTING") or time.time() - _last_check < RUN_EVERY:
        return
    with _guard:
        if time.time() - _last_check < RUN_EVERY:
            return
        _last_check = time.time()

    def work():
        try:
            run_all(app)
        except Exception as exc:
            print(f"[TASKS] {exc}")
    threading.Thread(target=work, daemon=True).start()


def send_task_reminders(now=None) -> int:
    """Email Aaron about tasks whose reminder date has arrived (once per date). Returns how many."""
    from flask import url_for

    from models import db
    from models.tasks import Task
    from routes.reviews_public import ADMIN_EMAIL
    from utils import email_html
    from utils.links import public_url
    now = now or dt.datetime.utcnow()
    due = (Task.query.filter(Task.status != "done", Task.remind_on.isnot(None), Task.remind_on <= now.date(),
                             Task.reminded_at.is_(None)).order_by(Task.remind_on).all())
    if not due:
        return 0
    lines = [f"• {t.ref} {t.title} ({t.tag})" for t in due]
    one = len(due) == 1
    last = due[0].notes[-1] if one and due[0].notes else None
    email_html.send(ADMIN_EMAIL, f"Reminder {due[0].ref}: {due[0].title}" if one else f"{len(due)} task reminders",
                    heading="Task reminder" if one else f"{len(due)} tasks to follow up",
                    lines=["You asked to be reminded about:"] + lines,
                    quote=last.body if last else None, quote_label=f"Latest note ({last.author_label})" if last else None,
                    button={"label": "Open the task" if one else "Open Tasks",
                            "url": public_url(url_for("admin.task", tid=due[0].id) if one else url_for("admin.tasks", show="due"))})
    for t in due:
        t.reminded_at = now
    db.session.commit()
    return len(due)


def send_jobs_today(now=None) -> int:
    """Each business with jobs booked today gets one morning email listing them (with links). Returns emails sent."""
    from flask import url_for

    from models import db
    from models.core import Account, SystemState
    from models.work import Lead
    from utils import email_html
    from utils.links import public_url
    from utils.task_mail import _client_emails
    now = now or dt.datetime.utcnow()
    day = now.date()
    start, end = dt.datetime.combine(day, dt.time()), dt.datetime.combine(day + dt.timedelta(days=1), dt.time())
    rows = (Lead.query.filter(Lead.status == "booked", Lead.archived_at.is_(None), Lead.start_at < end)
            .order_by(Lead.start_at).all())
    by_acc = {}
    for l in rows:
        if l.start_at >= start or l.end_at >= start:               # starts today, or a multi-day job running today
            by_acc.setdefault(l.account_id, []).append(l)
    sent = 0
    for acc_id, jobs in by_acc.items():
        key = f"jobs_today:{acc_id}:{day.isoformat()}"
        if db.session.get(SystemState, key):
            continue
        a = db.session.get(Account, acc_id)
        if not a or a.status != "active" or not a.has_feature("jobs"):
            continue
        to = _client_emails(a) if a.kind == "client" else [a.contact_email or "aaron@hapitech.dev"]
        if not to:
            continue
        lines = [f"• {l.start_at:%H:%M} {l.name}: {l.label}" + (f" ({l.postcode})" if l.postcode else "")
                 + (f", day {(day - l.start_at.date()).days + 1} of {l.days}" if l.days > 1 and l.start_at < start else "")
                 for l in jobs]
        one = len(jobs) == 1
        for addr in to:
            try:
                email_html.send(addr, f"Today: {jobs[0].name} at {jobs[0].start_at:%H:%M}" if one else f"Today: {len(jobs)} jobs",
                                account=a, heading="Your jobs today", lines=lines,
                                button={"label": "Open the job" if one else "Open your calendar",
                                        "url": public_url(url_for("portal.job", lid=jobs[0].id) if one else url_for("portal.calendar"))},
                                after=["Finished one? Tap “Job done ✓” on it to send the customer a review link."])
            except Exception as exc:
                print(f"[JOBS_TODAY] {addr}: {exc}")
        db.session.add(SystemState(key=key, value=str(len(jobs))))
        db.session.commit()
        sent += 1
    return sent
