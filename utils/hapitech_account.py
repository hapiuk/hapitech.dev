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
