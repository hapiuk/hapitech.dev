# models/tasks.py — Aaron's own to-do tickets (admin only; clients never see these).
# A task is tagged with a client, or with no client = "HapiTech infra". It can be linked to the change
# request it came from, carry a remind-on date (emailed when due) and a thread of notes from Aaron,
# Claude or the client (pasted in), used for instructions and additions.
import datetime as dt

from . import db
from .core import TimestampMixin, utcnow

TASK_STATUSES = [("todo", "To do"), ("doing", "Doing"), ("waiting", "Waiting"), ("done", "Done")]
NOTE_AUTHORS = [("aaron", "Me"), ("claude", "Claude"), ("client", "Client")]
INFRA = "HapiTech infra"


class Task(TimestampMixin, db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="todo")
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), index=True)          # None = HapiTech infra
    change_request_id = db.Column(db.Integer, db.ForeignKey("change_requests.id"), index=True)
    remind_on = db.Column(db.Date)
    reminded_at = db.Column(db.DateTime)               # reminder email sent for the current remind_on
    done_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    account = db.relationship("Account")
    change_request = db.relationship("ChangeRequest")
    notes = db.relationship("TaskNote", lazy=True, cascade="all, delete-orphan", order_by="TaskNote.created_at")

    @property
    def tag(self):
        return self.account.name if self.account else INFRA

    @property
    def status_label(self):
        return dict(TASK_STATUSES).get(self.status, self.status)

    @property
    def due(self):
        return self.status != "done" and self.remind_on is not None and self.remind_on <= dt.date.today()

    def set_status(self, status):
        if status not in dict(TASK_STATUSES) or status == self.status:
            return
        self.status = status
        self.done_at = dt.datetime.utcnow() if status == "done" else None
        if status == "done" and self.change_request and self.change_request.status != "done":
            self.change_request.status = "done"            # finishing the task closes the client's request

    def set_remind_on(self, day):
        if day != self.remind_on:
            self.remind_on, self.reminded_at = day, None


class TaskNote(db.Model):
    __tablename__ = "task_notes"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False, index=True)
    author_kind = db.Column(db.String(20), nullable=False, default="aaron")   # aaron | claude | client
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    @property
    def author_label(self):
        return {"aaron": "Aaron", "claude": "Claude", "client": "Client"}.get(self.author_kind, self.author_kind)


def open_for(account_id):
    return (Task.query.filter(Task.account_id == account_id, Task.status != "done")
            .order_by(Task.remind_on.asc().nullslast(), Task.created_at.desc()).all())


def due_count():
    return Task.query.filter(Task.status != "done", Task.remind_on.isnot(None),
                             Task.remind_on <= dt.date.today()).count()


def from_change_request(cr, user_id=None):
    """The task for an accepted change request (made once; later calls return the same task)."""
    t = Task.query.filter_by(change_request_id=cr.id).first()
    if t:
        return t, False
    first = (cr.body or "").strip().splitlines()[0] if (cr.body or "").strip() else "Change request"
    t = Task(title=f"Change: {first}"[:200], account_id=cr.account_id, change_request_id=cr.id,
             status="doing", created_by=user_id)
    t.notes.append(TaskNote(author_kind="client", body=cr.body or "", created_at=cr.created_at))
    db.session.add(t)
    return t, True
