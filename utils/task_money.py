# utils/task_money.py — prices, quotes and receipts on Tasks. HapiTech's quotes and invoices live on a job
# (Lead) in HapiTech's own Jobs, so a task that needs pricing gets one behind the scenes, linked both ways.
import datetime as dt
import json


def ensure_lead(t, user_id=None):
    """The HapiTech job behind a task (made if it has none). Needs a client to send things to."""
    from models import db
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    if t.lead:
        return t.lead
    a = t.account
    if not a:
        return None
    people = [u for u in a.users if u.role == "owner" and not u.is_admin]
    email = a.contact_email if a.kind == "client" else (people[0].email if people else a.contact_email)
    lead = Lead(account_id=hapitech().id, source="manual", status="accepted", name=(a.contact_name or a.name)[:120],
                email=email, for_account_id=a.id, title=t.title[:160], notes=f"For task {t.ref}")
    db.session.add(lead)
    db.session.flush()
    t.lead_id = lead.id
    t.lead = lead
    return lead


def money(t):
    """What the task is worth so far: its quotes, invoices and a headline price (None = not priced)."""
    lead = t.lead
    quotes = list(lead.quotes) if lead else []
    invoices = list(lead.invoices) if lead else []
    accepted = next((q for q in quotes if q.status == "accepted"), None)
    price = None
    if invoices:                                   # newest first
        price = invoices[0].totals[2]
    elif accepted or quotes:
        price = (accepted or quotes[0]).totals[2]
    return {"quotes": quotes, "invoices": invoices, "accepted": accepted, "price": price,
            "paid": next((i for i in invoices if i.status == "paid"), None),
            "sent": next((i for i in invoices if i.status == "sent"), None),
            "draft": next((i for i in invoices if i.status == "draft"), None)}


def mark_paid(t):
    """Confirm the task's (latest) sent invoice is paid; record it on the client's Money tab. Commits."""
    import datetime as _dt
    from models import db
    m = money(t)
    inv = next((i for i in m["invoices"] if i.status == "sent"), None)
    if inv is None:
        raise ValueError("There's no sent invoice waiting to be paid.")
    inv.status, inv.paid_at = "paid", _dt.datetime.utcnow()
    db.session.flush()
    record_payment(inv)
    db.session.commit()
    return inv


def make_receipt(t, user_id=None):
    """After it's paid: email the client a receipt for the paid invoice. Returns the invoice. Commits."""
    from models import db
    from utils import client_mail
    m = money(t)
    inv = m["paid"]
    if inv is None:
        raise ValueError("Mark the invoice as paid first, then send the receipt.")
    if not inv.lead.email:
        raise ValueError("The client has no email address. Add one on their client page first.")
    client_mail.send_receipt(inv)
    db.session.commit()
    return inv

def record_payment(inv):
    """A HapiTech invoice was paid: record it on the client's Money tab (once, ref = invoice number),
    so admin totals ("Paid this month", the client's history) include it. Doesn't commit."""
    from models import db
    from models.core import Account, Payment
    lead = inv.lead
    if not lead or not lead.account or lead.account.kind != "internal" or not lead.for_account_id:
        return None
    if Payment.query.filter_by(account_id=lead.for_account_id, ref=inv.number).first():
        return None
    p = Payment(account_id=lead.for_account_id, amount_gbp=inv.totals[2],
                paid_at=(inv.paid_at or dt.datetime.utcnow()).date(), method="invoice", ref=inv.number)
    db.session.add(p)
    return p
