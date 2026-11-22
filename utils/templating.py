# utils/templating.py — Jinja filters and globals shared by every template.
import datetime as dt
import json

from markupsafe import Markup, escape


def init_templating(app):
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
