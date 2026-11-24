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
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), index=True)              # a HapiTech job it came from
    shared = db.Column(db.Boolean, nullable=False, default=False)                       # the client can see + comment
    remind_on = db.Column(db.Date)
    reminded_at = db.Column(db.DateTime)               # reminder email sent for the current remind_on
    done_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    account = db.relationship("Account")
    change_request = db.relationship("ChangeRequest")
    lead = db.relationship("Lead")
    notes = db.relationship("TaskNote", lazy=True, cascade="all, delete-orphan", order_by="TaskNote.created_at")

    @property
    def ref(self):
        return f"T-{self.id}"

    @property
    def shared_notes(self):
        return [n for n in self.notes if n.shared]

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
        if self.lead:                                       # the HapiTech job it came from follows along
            if status == "done" and self.lead.status in ("new", "quoted", "accepted", "booked"):
                self.lead.status, self.lead.done_at = "done", self.done_at
            elif status != "done" and self.lead.status == "done":
                self.lead.status, self.lead.done_at = "accepted", None

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
    shared = db.Column(db.Boolean, nullable=False, default=False)      # shown to the client (client comments always are)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    author = db.relationship("User")

    @property
    def author_label(self):
        if self.author_kind == "client" and self.author and not self.author.is_admin:
            return self.author.name or self.author.email
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
             status="doing", created_by=user_id, shared=True)
    t.notes.append(TaskNote(author_kind="client", author_id=cr.created_by, body=cr.body or "", shared=True,
                            created_at=cr.created_at))
    db.session.add(t)
    return t, True


def parse_ref(q):
    """'T-12', 't12', '#12', '12' -> ("T", 12); 'R-3' -> ("R", 3); anything else -> (None, None)."""
    import re
    m = re.fullmatch(r"\s*#?\s*([TtRr])?\s*-?\s*(\d{1,9})\s*", q or "")
    if not m:
        return None, None
    return (m.group(1) or "T").upper(), int(m.group(2))


def text_filter(query, q, shared_only=False):
    """Narrow a Task query by an ID or words in the title / notes (clients: only notes they can see)."""
    kind, num = parse_ref(q)
    if kind == "T":
        return query.filter(Task.id == num)
    if kind == "R":
        return query.filter(Task.change_request_id == num)
    like = f"%{q.strip()}%"
    notes = db.session.query(TaskNote.task_id).filter(TaskNote.body.ilike(like))
    if shared_only:
        notes = notes.filter(TaskNote.shared.is_(True))
    return query.filter(db.or_(Task.title.ilike(like), Task.id.in_(notes)))


def from_lead(lead, account, user_id=None, status="todo"):
    """An accepted HapiTech job becomes a task under the client (once). Shared with the client unless it's
    a hapitech.report report about them."""
    t = Task.query.filter_by(lead_id=lead.id).first()
    if t:
        return t, False
    what = lead.title or ((lead.message or "").strip().splitlines() or [lead.name])[0]
    t = Task(title=(what or "Job")[:200], account_id=account.id if account else None, lead_id=lead.id,
             status=status, created_by=user_id, shared=bool(account) and lead.source != "report")
    if lead.message:
        t.notes.append(TaskNote(author_kind="client", body=lead.message, shared=t.shared, created_at=lead.created_at))
    if lead.notes:
        t.notes.append(TaskNote(author_kind="aaron", author_id=user_id, body=lead.notes, shared=False))
    db.session.add(t)
    return t, True
