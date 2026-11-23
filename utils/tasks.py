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
