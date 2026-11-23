# utils/nav.py — sidebar / tab-bar definitions for the admin and portal shells.
from flask import g, request, url_for

ICONS = {
    "home": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18.5 14.8c1.7.8 2.7 2.6 3 5.2"/>',
    "star": '<path d="m12 3 2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.5 6.7 19.4l1.2-6L3.4 9.3l6-.7z"/>',
    "chip": '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
    "play": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 9 5 3-5 3z"/>',
    "inbox": '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
    "cog": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "send": '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-8 8"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "lab": '<path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.7 3h10.6a2 2 0 0 0 1.7-3l-5-9V3"/><path d="M7.5 15h9"/>',
}


def _item(label, endpoint, icon, prefix=None, **kw):
    url = kw.pop("url", None) or url_for(endpoint, **kw.pop("args", {}))
    active_prefix = prefix or url
    path = request.path.rstrip("/") or "/"
    active = path == active_prefix.rstrip("/") or (prefix and path.startswith(prefix))
    return {"label": label, "url": url, "icon": ICONS[icon], "active": active, **kw}


def admin_nav(counts=None):
    c = counts or {}
    return [
        _item("Overview", "admin.home", "home", url="/admin", prefix=None),
        _item("Clients", "admin.clients", "users", prefix="/admin/clients"),
        _item("Clients' jobs", "admin.work", "briefcase", prefix="/admin/work"),
        _item("Reviews", "admin.reviews", "star", prefix="/admin/reviews", badge=c.get("reported")),
        _item("Change requests", "admin.change_requests", "inbox", prefix="/admin/requests", badge=c.get("requests")),
        _item("Updates for clients", "admin.updates", "send", prefix="/admin/updates"),
        {"section": "HapiTech Lab"},
        _item("Benchmark runs", "admin.bench_runs", "play", prefix="/admin/lab/runs"),
        _item("Prompts", "admin.bench_prompts", "doc", prefix="/admin/lab/prompts"),
        _item("Models", "admin.bench_models", "chip", prefix="/admin/lab/models"),
        {"section": "System"},
        _item("Settings", "admin.settings", "cog", prefix="/admin/settings"),
    ]


def portal_nav(counts=None, owner=True):
    c = counts or {}
    items = [
        _item("Home", "portal.home", "home", url="/portal", tab=True),
        _item("Jobs", "portal.jobs", "briefcase", prefix="/portal/jobs", tab=True, badge=c.get("new_jobs")),
        _item("Ask for a review", "portal.ask", "send", prefix="/portal/ask", tab=True, short="Ask", primary=True),
        _item("Reviews", "portal.reviews", "star", prefix="/portal/reviews", tab=True, badge=c.get("unreplied")),
        _item("Calendar", "portal.calendar", "calendar", prefix="/portal/calendar"),
        _item("Posts", "portal.posts", "image", prefix="/portal/posts"),
    ]
    if owner:
        items.append(_item("My website", "portal.website", "edit", prefix="/portal/website"))
        items.append(_item("Settings", "portal.settings", "cog", prefix="/portal/settings"))
    items.append(_item("Help", "portal.help", "help", prefix="/portal/help"))
    return items
