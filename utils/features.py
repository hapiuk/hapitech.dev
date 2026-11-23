# utils/features.py — dashboard sections a client can have. Most get everything; someone without a website
# from us might only want reviews. Home, My plan, Settings and Help are always there.
ALL = ("reviews", "website", "jobs")
LABELS = {"reviews": "Reviews (collect, ask, reply, review page)", "website": "Website (edit it, visitors, posts)",
          "jobs": "Jobs (enquiries, quotes, invoices, calendar)"}
PRESETS = {"all": list(ALL), "reviews": ["reviews"]}
PATHS = {"reviews": ("/portal/reviews", "/portal/ask", "/portal/requests"),
         "website": ("/portal/website", "/portal/visitors", "/portal/posts"),
         "jobs": ("/portal/jobs", "/portal/calendar")}


def needed(path):
    """The feature a portal page belongs to (None = always allowed)."""
    if path.startswith("/portal/requests/work"):
        return None
    for f, prefixes in PATHS.items():
        if any(path == p or path.startswith(p + "/") for p in prefixes):
            return f
    return None
