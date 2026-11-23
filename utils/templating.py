# utils/templating.py — Jinja filters and globals shared by every template.
import datetime as dt
import json

from markupsafe import Markup, escape


def init_templating(app):
    app.jinja_env.globals["ed"] = lambda key: ed(key)
    app.jinja_env.filters["richtext"] = lambda v: richtext(v)
    def media_by_id(mid):
        from models import db
        from models.content import Media
        return db.session.get(Media, mid) if isinstance(mid, int) else None

    @app.context_processor
    def _globals():
        return {"current_year": dt.datetime.utcnow().year, "now": dt.datetime.utcnow(), "media_by_id": media_by_id}

    @app.template_filter("gbp")
    def gbp(v, pence=False):
        try:
            n = float(v or 0)
        except (TypeError, ValueError):
            return "£0"
        return f"£{n:,.2f}" if pence or n % 1 else f"£{n:,.0f}"

    @app.template_filter("ukdate")
    def ukdate(v, fmt="%-d %b %Y"):
        if not v:
            return ""
        if isinstance(v, str):
            try:
                v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return v
        return v.strftime(fmt)

    @app.template_filter("ago")
    def ago(v):
        if not v:
            return ""
        if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
            v = dt.datetime.combine(v, dt.time())
        secs = (dt.datetime.utcnow() - v.replace(tzinfo=None)).total_seconds()
        if secs < 60:
            return "just now"
        for size, unit in ((86400 * 365, "year"), (86400 * 30, "month"), (86400 * 7, "week"),
                           (86400, "day"), (3600, "hour"), (60, "minute")):
            if secs >= size:
                n = int(secs // size)
                return f"{n} {unit}{'s' if n != 1 else ''} ago"
        return ""

    @app.template_filter("age")
    def age(v):
        """How old a review is, by the day: today, yesterday, 5 days ago, 3 weeks ago, 4 months ago, 2 years ago."""
        if not v:
            return ""
        d = (dt.date.today() - (v.date() if isinstance(v, dt.datetime) else v)).days
        if d <= 0:
            return "today"
        if d == 1:
            return "yesterday"
        for size, unit in ((365, "year"), (30, "month"), (7, "week"), (1, "day")):
            if d >= size:
                n = d // size
                return f"{n} {unit}{'s' if n != 1 else ''} ago"
        return ""

    @app.template_filter("stars")
    def stars(n):
        n = max(0, min(5, int(n or 0)))
        return Markup(f'<span class="stars" role="img" aria-label="{n} out of 5 stars">'
                      + "★" * n + f'<span class="stars__off">{"★" * (5 - n)}</span></span>')

    @app.template_filter("fromjson")
    def fromjson(s):
        try:
            return json.loads(s or "null")
        except (TypeError, ValueError):
            return None

    @app.template_filter("nl2br")
    def nl2br(s):
        return Markup("<br>".join(escape(s or "").split("\n")))


# ---------------------------------------------------------------- HapiTech's own sites: edited text from My website

def _own_edits():
    """{key: text} of the sections edited in My website for the site being shown (hapitech.dev or hapitech.report)."""
    from flask import g, request
    slug = "hapitech-reviews" if (request.blueprint or "") == "hub" else "hapitech"
    cache = getattr(g, "_own_edits", None)
    if cache is None:
        cache = g._own_edits = {}
    if slug not in cache:
        out = {}
        try:
            from models.content import ContentBlock
            from models.core import Account
            a = Account.query.filter_by(slug=slug).first()
            if a:
                for b in ContentBlock.query.filter_by(account_id=a.id).all():
                    if b.value != b.default_value and isinstance(b.data, str) and b.data.strip():
                        out[b.key] = b.data
        except Exception as exc:                 # never break the public site over an edit
            print(f"[OWN_EDITS] {exc}")
        cache[slug] = out
    return cache[slug]


def ed(key):
    return _own_edits().get(key)


def richtext(s):
    """Edited text → safe HTML: **bold**, new lines kept."""
    import re as _re

    from markupsafe import Markup, escape
    t = str(escape(s or ""))
    t = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return Markup(t.replace("\n", "<br>"))
