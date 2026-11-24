# routes/portal_requests.py — the client's "Requests" page: what they've asked Aaron for (change requests, R-3)
# and the tasks Aaron has shared with them (T-12), with statuses, search by ID or words, and comments.
# A client only ever sees their own account's change requests and SHARED tasks, and only the shared notes on them.
import datetime as dt

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from models.core import ChangeRequest
from models.tasks import Task, TaskNote, parse_ref, text_filter
from utils import task_mail
from utils.security import owner_required, scoped

from .portal import portal_bp


def _shared_tasks():
    return Task.query.filter(Task.account_id == g.account.id, Task.shared.is_(True))


def new_request(body):
    """A client asks for something: saved as a change request, Aaron is emailed with a direct link."""
    cr = ChangeRequest(account_id=g.account.id, body=body[:5000], created_by=current_user.id)
    db.session.add(cr)
    db.session.commit()
    task_mail.tell_aaron_new_request(cr, current_user)
    return cr


@portal_bp.route("/changes", methods=["GET", "POST"])
@owner_required
def changes():
    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        provider = (request.form.get("provider") or "").strip()[:80]
        if provider and not body:                    # Settings → "Use a different payment provider? Ask us"
            body = f"Please add a payment provider for my invoices: {provider}"
        if not body:
            flash("Describe what you'd like.", "err")
            return redirect(url_for("portal.changes"))
        cr = new_request(body)
        flash(f"Sent to Aaron as {cr.ref}. You'll get an email when he picks it up.", "ok")
        return redirect(url_for("portal.request_cr", rid=cr.id))
    q = (request.args.get("q") or "").strip()
    kind, num = parse_ref(q)
    if q and kind == "T" and _shared_tasks().filter(Task.id == num).first() and q.upper().lstrip("# ").startswith("T"):
        return redirect(url_for("portal.request_task", tid=num))
    if q and kind == "R" and scoped(ChangeRequest, id=num).first():
        return redirect(url_for("portal.request_cr", rid=num))
    tasks_q = _shared_tasks()
    crs_q = scoped(ChangeRequest)
    if q:
        tasks_q = text_filter(tasks_q, q, shared_only=True)
        crs_q = crs_q.filter(ChangeRequest.id == num) if kind == "R" else crs_q.filter(ChangeRequest.body.ilike(f"%{q}%"))
    tasks = tasks_q.limit(200).all()
    linked = {t.change_request_id for t in Task.query.filter(Task.account_id == g.account.id,
                                                             Task.change_request_id.isnot(None))}
    crs = [r for r in crs_q.limit(200).all() if r.id not in linked]       # not picked up yet (or closed without a task)
    # one list: open things first (newest activity first), finished ones at the bottom
    items = [{"kind": "cr", "r": r, "done": r.status == "done", "at": r.created_at} for r in crs] + \
            [{"kind": "task", "t": t, "done": t.status == "done", "at": t.updated_at} for t in tasks]
    items.sort(key=lambda i: (i["done"], -i["at"].timestamp()))
    return render_template("portal/requests.html", items=items, q=q)


@portal_bp.route("/changes/T-<int:tid>", methods=["GET", "POST"])
@owner_required
def request_task(tid):
    t = _shared_tasks().filter(Task.id == tid).first() or abort(404)
    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if body:
            admin = current_user.is_admin                     # Aaron viewing as the client: his own reply
            n = TaskNote(author_kind="aaron" if admin else "client", author_id=current_user.id,
                         body=body[:5000], shared=True)
            t.notes.append(n)
            t.updated_at = dt.datetime.utcnow()
            db.session.commit()
            if admin:
                task_mail.tell_client_task(t, "Aaron replied", "Aaron replied", [], quote=n.body, quote_label="Aaron wrote")
            else:
                task_mail.tell_aaron_comment(t, n, current_user)
            flash("Sent to Aaron." if not admin else "Reply sent.", "ok")
        return redirect(url_for("portal.request_task", tid=t.id) + "#reply")
    return render_template("portal/request.html", t=t, cr=t.change_request, notes=t.shared_notes)


@portal_bp.route("/changes/R-<int:rid>")
@owner_required
def request_cr(rid):
    cr = scoped(ChangeRequest, id=rid).first() or abort(404)
    t = cr.task
    if t and t.shared:
        return redirect(url_for("portal.request_task", tid=t.id))
    return render_template("portal/request.html", t=None, cr=cr, notes=[])
