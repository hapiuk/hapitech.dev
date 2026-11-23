# utils/traffic.py — visitor numbers for a client site, from the cookie-free daily counts the site reports.
import datetime as dt

from models import db
from models.content import SiteVisit

SOURCE_NAMES = {"": "Typed in / bookmarks / apps", "google": "Google", "bing": "Bing", "duckduckgo": "DuckDuckGo",
                "facebook": "Facebook", "m": "Facebook", "l": "Facebook", "lm": "Facebook", "instagram": "Instagram",
                "linkedin": "LinkedIn", "lnkd": "LinkedIn", "t": "X (Twitter)", "x": "X (Twitter)", "yahoo": "Yahoo",
                "hapitech": "HapiTech", "checkatrade": "Checkatrade", "yell": "Yell", "nextdoor": "Nextdoor",
                "whatsapp": "WhatsApp"}
PAGE_NAMES = {"/": "Homepage", "/privacy": "Privacy", "/terms": "Terms", "/posts": "Posts"}


def _total(account_id, start, end):
    return db.session.query(db.func.coalesce(db.func.sum(SiteVisit.count), 0)).filter(
        SiteVisit.account_id == account_id, SiteVisit.day >= start, SiteVisit.day <= end).scalar() or 0


def summary(account, days=30):
    today = dt.date.today()
    start = today - dt.timedelta(days=days - 1)
    prev_start, prev_end = start - dt.timedelta(days=days), start - dt.timedelta(days=1)
    total, previous = _total(account.id, start, today), _total(account.id, prev_start, prev_end)

    per_day = dict(db.session.query(SiteVisit.day, db.func.sum(SiteVisit.count)).filter(
        SiteVisit.account_id == account.id, SiteVisit.day >= start).group_by(SiteVisit.day).all())
    daily = [(start + dt.timedelta(days=i), int(per_day.get(start + dt.timedelta(days=i), 0))) for i in range(days)]
    peak = max((n for _, n in daily), default=0) or 1

    sources = {}
    for ref, n in db.session.query(SiteVisit.ref, db.func.sum(SiteVisit.count)).filter(
            SiteVisit.account_id == account.id, SiteVisit.day >= start).group_by(SiteVisit.ref).all():
        name = SOURCE_NAMES.get(ref, ref.title() if ref else SOURCE_NAMES[""])
        sources[name] = sources.get(name, 0) + int(n)
    pages = {}
    for path, n in db.session.query(SiteVisit.path, db.func.sum(SiteVisit.count)).filter(
            SiteVisit.account_id == account.id, SiteVisit.day >= start).group_by(SiteVisit.path).all():
        name = PAGE_NAMES.get(path) or (f"Work in {path[6:].replace('-', ' ').title()}" if path.startswith("/work/") else path)
        pages[name] = pages.get(name, 0) + int(n)

    change = None if not previous else round((total - previous) * 100 / previous)
    return {"days": days, "total": int(total), "previous": int(previous), "change": change,
            "daily": daily, "peak": peak,
            "sources": sorted(sources.items(), key=lambda x: -x[1])[:6],
            "pages": sorted(pages.items(), key=lambda x: -x[1])[:6],
            "google": sources.get("Google", 0)}
