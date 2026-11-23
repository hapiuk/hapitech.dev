# routes/admin/tasks.py — Tasks: Aaron's own to-do tickets (client-tagged or "HapiTech infra"),
# with reminders, a notes thread (Aaron / Claude / Client) and links to accepted change requests.
import datetime as dt

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.core import Account, ChangeRequest
from models.tasks import NOTE_AUTHORS, TASK_STATUSES, Task, TaskNote

from . import admin_bp

SHOWS = [("open", "Open"), ("due", "Reminders due"), ("waiting", "Waiting"), ("done", "Done"), ("all", "All")]


def _accounts():
    return (Account.query.filter(Account.kind.in_(["client", "internal"]), Account.status != "archived")
            .order_by(Account.kind, Account.name).all())


def _parse_day(v):
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _account_from(v):
    """Form value: "" / "infra" = HapiTech infra, otherwise an account slug."""
    if not v or v == "infra":
        return None
    return Account.query.filter_by(slug=v).first()


@admin_bp.route("/tasks")
def tasks():
    show = request.args.get("show", "open")
    tag = request.args.get("for", "")
    q = Task.query
    if show == "open":
        q = q.filter(Task.status != "done")
    elif show == "due":
        q = q.filter(Task.status != "done", Task.remind_on.isnot(None), Task.remind_on <= dt.date.today())
    elif show in ("waiting", "done"):
        q = q.filter(Task.status == show)
    if tag == "infra":
        q = q.filter(Task.account_id.is_(None))
    elif tag:
        a = Account.query.filter_by(slug=tag).first()
        q = q.filter(Task.account_id == (a.id if a else -1))
    order = db.case((Task.status == "doing", 0), (Task.status == "todo", 1), (Task.status == "waiting", 2), else_=3)
    rows = q.order_by(order, Task.remind_on.asc().nullslast(), Task.updated_at.desc()).limit(300).all()
    return render_template("admin/tasks.html", rows=rows, show=show, tag=tag, shows=SHOWS, accounts=_accounts(),
                           today=dt.date.today())


@admin_bp.route("/tasks/new", methods=["GET", "POST"])
def task_new():
    if request.method == "POST":
        f = request.form
        title = (f.get("title") or "").strip()[:200]
        if not title:
            flash("Give the task a title.", "err")
            return redirect(url_for("admin.task_new", **{"for": f.get("for", "")}))
        a = _account_from(f.get("for"))
        t = Task(title=title, account_id=a.id if a else None, created_by=current_user.id)
        t.set_status(f.get("status") or "todo")
        t.set_remind_on(_parse_day(f.get("remind_on")))
        body = (f.get("note") or "").strip()
        if body:
            t.notes.append(TaskNote(author_kind=f.get("author") if f.get("author") in dict(NOTE_AUTHORS) else "aaron",
                                    author_id=current_user.id, body=body[:20000]))
        db.session.add(t)
        db.session.commit()
        flash("Task added.", "ok")
        return redirect(url_for("admin.task", tid=t.id))
    return render_template("admin/task.html", t=None, accounts=_accounts(), statuses=TASK_STATUSES,
                           authors=NOTE_AUTHORS, preset=request.args.get("for", ""), today=dt.date.today())


@admin_bp.route("/tasks/<int:tid>", methods=["GET", "POST"])
def task(tid):
    t = db.session.get(Task, tid) or abort(404)
    if request.method == "POST":
        f = request.form
        action = f.get("action")
        if action == "note":
            body = (f.get("note") or "").strip()
            if body:
                kind = f.get("author") if f.get("author") in dict(NOTE_AUTHORS) else "aaron"
                t.notes.append(TaskNote(author_kind=kind, author_id=current_user.id, body=body[:20000]))
                t.updated_at = dt.datetime.utcnow()
        elif action == "save":
            title = (f.get("title") or "").strip()[:200]
            if title:
                t.title = title
            a = _account_from(f.get("for"))
            t.account_id = a.id if a else None
            t.set_status(f.get("status") or t.status)
            t.set_remind_on(_parse_day(f.get("remind_on")))
            flash("Saved.", "ok")
        elif action == "status":
            t.set_status(f.get("status"))
        elif action == "snooze":
            days = {"1d": 1, "1w": 7, "2w": 14, "1m": 30}.get(f.get("by"), 7)
            t.set_remind_on(dt.date.today() + dt.timedelta(days=days))
        elif action == "clear_reminder":
            t.set_remind_on(None)
        elif action == "delete_note":
            n = db.session.get(TaskNote, int(f.get("nid") or 0))
            if n and n.task_id == t.id:
                db.session.delete(n)
        elif action == "delete":
            db.session.delete(t)
            db.session.commit()
            flash("Task deleted.", "ok")
            return redirect(url_for("admin.tasks"))
        db.session.commit()
        return redirect(url_for("admin.task", tid=t.id) + ("#notes" if action in ("note", "delete_note") else ""))
    return render_template("admin/task.html", t=t, accounts=_accounts(), statuses=TASK_STATUSES,
                           authors=NOTE_AUTHORS, preset="", today=dt.date.today())


@admin_bp.route("/requests/<int:rid>/task", methods=["POST"])
def change_request_task(rid):
    """Turn a change request into a task (or open the one it already has)."""
    from models.tasks import from_change_request
    cr = db.session.get(ChangeRequest, rid) or abort(404)
    if cr.status == "new":
        cr.status = "doing"
    t, _ = from_change_request(cr, current_user.id)
    db.session.commit()
    return redirect(url_for("admin.task", tid=t.id))
