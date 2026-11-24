# routes/admin/tasks.py — Tasks: Aaron's to-do tickets (client-tagged or "HapiTech infra"), with reminders,
# a notes thread (Me / Claude / Client), links to accepted change requests and HapiTech jobs, and IDs (T-12).
# A task can be shared with its client: they see it (and only its shared notes) in their dashboard and can comment.
# Only admins reach these routes, so only Aaron can edit or delete.
import datetime as dt

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.core import Account, ChangeRequest
from models.tasks import NOTE_AUTHORS, TASK_STATUSES, Task, TaskNote, parse_ref, text_filter
from utils import task_mail

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


def change_status(t, status):
    """Set a task's status and tell the client if it's shared. Returns True if it changed."""
    before = t.status
    t.set_status(status)
    if t.status == before:
        return False
    if t.shared and t.status in ("doing", "done"):
        words = {"doing": ("Aaron's working on it", ["Aaron has started on this."]),
                 "done": ("Done ✓", ["Aaron has marked this as done. If anything's not right, reply on the page."])}
        heading, lines = words[t.status]
        task_mail.tell_client_task(t, "Update" if t.status == "doing" else "Done", heading, lines)
    return True


def filtered(show="open", tag="", q=""):
    query = Task.query
    if show == "open":
        query = query.filter(Task.status != "done")
    elif show == "due":
        query = query.filter(Task.status != "done", Task.remind_on.isnot(None), Task.remind_on <= dt.date.today())
    elif show in ("waiting", "done"):
        query = query.filter(Task.status == show)
    if tag == "infra":
        query = query.filter(Task.account_id.is_(None))
    elif tag:
        a = Account.query.filter_by(slug=tag).first()
        query = query.filter(Task.account_id == (a.id if a else -1))
    if q:
        query = text_filter(query, q)
    order = db.case((Task.status == "doing", 0), (Task.status == "todo", 1), (Task.status == "waiting", 2), else_=3)
    return query.order_by(order, Task.remind_on.asc().nullslast(), Task.updated_at.desc())


@admin_bp.route("/tasks")
def tasks():
    show, tag, q = request.args.get("show", "open"), request.args.get("for", ""), (request.args.get("q") or "").strip()
    kind, num = parse_ref(q)
    if kind == "T" and db.session.get(Task, num) and q.strip().upper().startswith(("T", "#")):
        return redirect(url_for("admin.task", tid=num))            # "T-12" jumps straight to the task
    if kind == "R":
        cr = db.session.get(ChangeRequest, num)
        if cr:
            t = cr.task
            return redirect(url_for("admin.task", tid=t.id) if t else url_for("admin.change_requests", r=cr.id) + f"#r{cr.id}")
    rows = filtered("all" if q else show, tag, q).limit(300).all()
    return render_template("admin/tasks.html", rows=rows, show=show, tag=tag, q=q, shows=SHOWS, accounts=_accounts(),
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
        t = Task(title=title, account_id=a.id if a else None, created_by=current_user.id,
                 shared=bool(a) and bool(f.get("shared")))
        t.set_status(f.get("status") or "todo")
        t.set_remind_on(_parse_day(f.get("remind_on")))
        body = (f.get("note") or "").strip()
        if body:
            kind = f.get("author") if f.get("author") in dict(NOTE_AUTHORS) else "aaron"
            t.notes.append(TaskNote(author_kind=kind, author_id=current_user.id, body=body[:20000],
                                    shared=t.shared and kind != "claude" and bool(f.get("note_shared"))))
        db.session.add(t)
        db.session.commit()
        if t.shared:
            task_mail.tell_client_task(t, "New from Aaron", "Aaron added something for you",
                                       ["Aaron has added this to your requests. You can follow it and reply in your dashboard."])
        flash(f"Task {t.ref} added.", "ok")
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
                n = TaskNote(author_kind=kind, author_id=current_user.id, body=body[:20000],
                             shared=t.shared and kind != "claude" and bool(f.get("note_shared")))
                t.notes.append(n)
                t.updated_at = dt.datetime.utcnow()
                db.session.commit()
                if n.shared and kind == "aaron":
                    task_mail.tell_client_task(t, "Aaron replied", "Aaron replied", [], quote=n.body, quote_label="Aaron wrote")
                flash("Note added" + (" and sent to the client." if n.shared else " (private)."), "ok")
        elif action == "save":
            title = (f.get("title") or "").strip()[:200]
            if title:
                t.title = title
            a = _account_from(f.get("for"))
            t.account_id = a.id if a else None
            t.shared = bool(a) and bool(f.get("shared"))
            t.set_remind_on(_parse_day(f.get("remind_on")))
            change_status(t, f.get("status") or t.status)
            flash("Saved.", "ok")
        elif action == "status":
            if change_status(t, f.get("status")) and t.status == "done" and t.account:
                flash("Done ✓. You can send a receipt from the Money panel.", "ok")
        elif action == "share":
            t.shared = bool(t.account) and f.get("on") == "1"
            flash(f"Now {'visible to ' + t.account.name if t.shared else 'private'}.", "ok")
        elif action == "note_share":
            n = db.session.get(TaskNote, int(f.get("nid") or 0))
            if n and n.task_id == t.id and n.author_kind != "claude":
                n.shared = t.shared and f.get("on") == "1"
        elif action in ("quote", "invoice"):
            from utils.task_money import ensure_lead
            lead = ensure_lead(t, current_user.id)
            if lead is None:
                flash("Set who the task is for first (a client), then add a quote.", "err")
            else:
                db.session.commit()
                return redirect(url_for("portal.priced", lid=lead.id, kind=action, **{"as": "hapitech"}))
        elif action == "receipt":
            from utils.task_money import make_receipt
            try:
                inv = make_receipt(t, current_user.id)
                flash(f"Receipt {inv.number} emailed to {inv.lead.email}.", "ok")
            except Exception as exc:
                db.session.rollback()
                flash(f"Couldn't send the receipt: {exc}", "err")
            return redirect(url_for("admin.task", tid=t.id) + "#money")
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
            flash(f"Task {t.ref} deleted.", "ok")
            return redirect(url_for("admin.tasks"))
        db.session.commit()
        return redirect(url_for("admin.task", tid=t.id) + ("#notes" if action in ("note", "delete_note", "note_share") else ""))
    from utils.task_money import money
    return render_template("admin/task.html", t=t, accounts=_accounts(), statuses=TASK_STATUSES,
                           authors=NOTE_AUTHORS, preset="", today=dt.date.today(), m=money(t))


def accept_change_request(cr):
    """Accepting a change request: it becomes a shared task, and the client is told (once)."""
    from models.tasks import from_change_request
    if cr.status == "new":
        cr.status = "doing"
    t, made = from_change_request(cr, current_user.id)
    db.session.commit()
    if made:
        task_mail.tell_client_task(t, "Accepted", "Aaron's on it",
                                   [f"Your request {cr.ref} has been accepted. You can follow it and reply here."])
    return t, made


@admin_bp.route("/requests/<int:rid>/task", methods=["POST"])
def change_request_task(rid):
    """Turn a change request into a task (or open the one it already has)."""
    cr = db.session.get(ChangeRequest, rid) or abort(404)
    t, _ = accept_change_request(cr)
    return redirect(url_for("admin.task", tid=t.id))
