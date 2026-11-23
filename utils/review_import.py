# utils/review_import.py — import reviews copied from a Google Business Profile ("select all, copy" of the reviews
# list), including the owner's replies. Google's copy has no star ratings, so ratings default to 5 unless listed
# in RATINGS below (checked by hand). Dates are approximate ("7 months ago" counted back from the copy date).
import datetime as dt
import re

REL = re.compile(r"^(Edited )?(a|an|\d+) (day|week|month|year)s? ago(New)?$")
META = re.compile(r"^(Local Guide·)?\d+ reviews?(·\d+ photos?)?$")
PHOTO = re.compile(r"^Photo \d+ in review by ")
REACT = re.compile(r"^(❤️|🙏|👍)\d+$")
PRICE = {"Great price", "Reasonable price", "Overpriced"}
OWNER = re.compile(r"^.+ \(owner\)$")
# star ratings that aren't 5, from the review text / the owner's reply (Google's copy doesn't include stars)
RATINGS = {("ray-g-handyman", "Donna Latham"): 1, ("ray-g-handyman", "Philip Edwards"): 1}
# Google display name -> the name already used on the site
ALIASES = {"catherinewatkins83": "Catherine Watkins"}


def rel_date(text, base):
    m = REL.match(text.strip())
    if not m:
        return None
    n = 1 if m.group(2) in ("a", "an") else int(m.group(2))
    unit = m.group(3)
    if unit == "day":
        return base - dt.timedelta(days=n)
    if unit == "week":
        return base - dt.timedelta(weeks=n)
    from utils.plans import add_months
    return add_months(base, -n if unit == "month" else -12 * n)


def _is_start(lines, i):
    """Line i is a reviewer's name: followed by a reviews-count line or straight by a date."""
    if i + 1 >= len(lines) or OWNER.match(lines[i]) or not lines[i].strip():
        return False
    nxt = lines[i + 1].strip()
    return bool(META.match(nxt) or REL.match(nxt))


def parse(text, base):
    lines = [l.rstrip() for l in text.splitlines()]
    out, i = [], 0
    while i < len(lines):
        if not _is_start(lines, i):
            i += 1
            continue
        r = {"name": lines[i].strip(), "photos": 0, "price": None, "body": [], "reply": None, "reply_date": None}
        i += 1
        if META.match(lines[i].strip()):
            m = re.search(r"·(\d+) photos?", lines[i])
            i += 1
        r["date"] = rel_date(lines[i], base)
        i += 1
        if i < len(lines) and lines[i].strip() in PRICE:
            r["price"] = lines[i].strip()
            i += 1
        # body until photos / reactions / owner reply / next review
        while i < len(lines) and not OWNER.match(lines[i]) and not _is_start(lines, i):
            l = lines[i].strip()
            if PHOTO.match(l):
                r["photos"] += 1
            elif REACT.match(l) or l in PRICE:
                pass
            else:
                r["body"].append(l)
            i += 1
        if i < len(lines) and OWNER.match(lines[i]):
            r["reply_date"] = rel_date(lines[i + 1], base) if i + 1 < len(lines) else None
            i += 2
            reply = []
            while i < len(lines) and not _is_start(lines, i):
                reply.append(lines[i].strip())
                i += 1
            r["reply"] = "\n".join(reply).strip().strip("“”\"").strip() or None
        body = "\n".join(r["body"]).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if body.endswith("… More"):
            body = body[: -len("… More")].rstrip() + "…"
        elif body.endswith("More") and body[:-4].rstrip().endswith("…"):
            body = body[:-4].rstrip()
        r["body"] = body
        out.append(r)
    return out


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def import_google(account, text, base, dry_run=False):
    """Add / update an account's Google reviews from a copied list. Returns a summary dict."""
    import datetime as _dt

    from models import db
    from models.reviews import Review, ReviewReply
    rows = parse(text, base)
    existing = {_norm(r.author_name): r for r in Review.query.filter_by(account_id=account.id, source="google").all()}
    added, updated = [], []
    for pos, g in enumerate(rows):
        name = ALIASES.get(g["name"].lower(), g["name"])
        r = existing.get(_norm(name)) or existing.get(_norm(g["name"]))
        when = _dt.datetime.combine(g["date"], _dt.time(12)) if g["date"] else None
        rating = RATINGS.get((account.slug, g["name"]), 5)
        if r is None:
            r = Review(account_id=account.id, source="google", author_name=name[:120], rating=rating, body=g["body"],
                       status="published", verified=False, external_id=f"google-copy:{_norm(g['name'])}")
            db.session.add(r)
            added.append(name)
        else:
            # keep the longer text we already have if Google's copy was cut short ("…")
            if g["body"] and not (g["body"].endswith("…") and _norm(r.body).startswith(_norm(g["body"][:-1])[:60])):
                r.body = g["body"]
            r.rating = rating if (account.slug, g["name"]) in RATINGS else r.rating
            updated.append(name)
        r.reviewed_at, r.sort_hint = when, pos
        r.photo_count, r.price_tag = g["photos"], g["price"]
        r.source_url = account.google_reviews_url or r.source_url
        db.session.flush()
        if g["reply"]:
            rep = r.replies[-1] if r.replies else None
            if rep is None:
                rep = ReviewReply(review_id=r.id, body=g["reply"])
                db.session.add(rep)
            rep.body = g["reply"]
            if g["reply_date"]:
                rep.created_at = _dt.datetime.combine(g["reply_date"], _dt.time(12))
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return {"parsed": len(rows), "added": added, "updated": updated,
            "not_five": [(n, s) for (slug, n), s in RATINGS.items() if slug == account.slug]}
