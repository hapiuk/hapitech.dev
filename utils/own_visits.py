# utils/own_visits.py — visitor counts for HapiTech's own sites (hapitech.dev, hapitech.report), the same way
# the client sites count theirs: day + page + the site people came from. No cookie, no IP, nothing per person.
import datetime as dt

BOT_WORDS = ("bot", "crawl", "spider", "slurp", "preview", "monitor", "curl", "python", "wget", "headless", "facebookexternalhit")


def _ref(referrer):
    host = (referrer or "").split("//", 1)[-1].split("/", 1)[0].lower()
    if not host or "hapitech" in host:
        return ""
    parts = host.replace("www.", "").split(".")
    return (parts[-3] if len(parts) > 2 and parts[-2] in ("co", "com", "org") else parts[0])[:100]


def count(slug, path):
    """Add one page view for the own-site account `slug`. Never raises."""
    from flask import request
    ua = (request.headers.get("User-Agent") or "").lower()
    if request.method != "GET" or not ua or any(w in ua for w in BOT_WORDS):
        return
    try:
        from models import db
        from models.content import SiteVisit
        from models.core import Account
        a = Account.query.filter_by(slug=slug).first()
        if not a:
            return
        day, ref, path = dt.date.today(), _ref(request.referrer), (path or "/")[:200]
        row = SiteVisit.query.filter_by(account_id=a.id, day=day, path=path, ref=ref).first()
        if row is None:
            row = SiteVisit(account_id=a.id, day=day, path=path, ref=ref, count=0)
            db.session.add(row)
        row.count += 1
        db.session.commit()
    except Exception as exc:
        print(f"[OWN_VISIT] {exc}")
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
