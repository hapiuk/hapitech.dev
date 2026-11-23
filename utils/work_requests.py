# utils/work_requests.py — clients asking HapiTech for extra work (changes, new features, rework, a new site).
# Each request is a job in HapiTech's own Jobs (so Aaron can quote, book and invoice it with the normal tools),
# linked back to the client so they can follow it on their dashboard.
from decimal import Decimal, InvalidOperation

KINDS = [("change", "A change to my website"), ("feature", "A new feature or page"), ("rework", "Rework something"),
         ("other", "Something else")]
CLIENT_STATUS = {"new": ("Received", ""), "quoted": ("Quote sent", "badge--acc"), "accepted": ("Accepted", "badge--ok"),
                 "booked": ("Booked in", "badge--ok"), "done": ("Done ✓", "badge--ok"), "declined": ("Not going ahead", "")}


def parse_offer(raw):
    raw = (raw or "").replace("£", "").replace(",", "").strip()
    if not raw:
        return None
    try:
        v = Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return v if v > 0 else None


def for_client(account):
    from models.work import Lead
    return (Lead.query.filter(Lead.for_account_id == account.id, Lead.source == "request")
            .order_by(Lead.created_at.desc()).all())


def create(account, user, kind, what, offer):
    from flask import url_for

    from models import db
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    from utils.links import public_url
    ht = hapitech()
    label = dict(KINDS).get(kind, "Something else")
    first = what.strip().splitlines()[0][:110]
    lead = Lead(account_id=ht.id, source="request", for_account_id=account.id, name=account.name,
                email=user.email, phone=account.contact_phone, title=f"{label}: {first}"[:160], message=what,
                offer_gbp=offer,
                notes=f"Requested by {user.name or user.email} from their dashboard. "
                      + (f"They offered £{offer:,.2f}." if offer else "No price offered: send them a quote."))
    db.session.add(lead)
    db.session.commit()
    try:
        from utils import email_html
        email_html.send("aaron@hapitech.dev", f"Work request from {account.name}: {first[:60]}",
                        heading=f"{account.name} would like some work done",
                        lines=[f"{user.name or user.email} asked for: {label.lower()}.", what],
                        box=[("Business", account.name), ("Offer", f"£{offer:,.2f}" if offer else "None: quote them"),
                             ("Their email", user.email)],
                        button={"label": "Open it in your jobs", "url": public_url(url_for("portal.job", lid=lead.id, **{"as": ht.slug}))},
                        reply_to=user.email)
    except Exception as exc:
        print(f"[WORK_REQUEST_NOTIFY] {exc}")
    return lead
