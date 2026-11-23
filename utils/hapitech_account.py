# utils/hapitech_account.py — HapiTech's own account, so Aaron can post updates and collect reviews on
# hapitech.dev using exactly the same screens the clients use (a good test of theirs, too).
SLUG = "hapitech"


def get(create=True):
    from models import db
    from models.core import Account, AddOn
    a = Account.query.filter_by(slug=SLUG).first()
    if a is None and create:
        a = Account(kind="internal", slug=SLUG, name="HapiTech", domain="hapitech.dev", trade="Websites, AI & IT",
                    contact_name="Aaron", contact_email="aaron@hapitech.dev", brand_colour="#2563eb")
        db.session.add(a)
        db.session.flush()
        db.session.add(AddOn(account_id=a.id, kind="reviews_updates", status="active"))
        db.session.commit()
    return a


# HapiTech's own sites, listed under Clients (tagged "Ours", never charged) so each can be managed on its own.
OWN_SITES = [
    {"slug": "hapitech-reviews", "name": "HapiTech Reviews", "domain": "hapitech.report", "trade": "Reviews of local businesses"},
]


def ensure_own_sites():
    """Create any missing own-site accounts (kind "internal": no invites, not on hapitech.report's list, no costs)."""
    from models import db
    from models.core import Account, AddOn
    get()
    added = 0
    for d in OWN_SITES:
        if Account.query.filter_by(slug=d["slug"]).first():
            continue
        a = Account(kind="internal", contact_name="Aaron", contact_email="aaron@hapitech.dev", brand_colour="#2563eb", **d)
        db.session.add(a)
        db.session.flush()
        db.session.add(AddOn(account_id=a.id, kind="reviews_updates", status="active"))
        added += 1
    db.session.commit()
    return added
