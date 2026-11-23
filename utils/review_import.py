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


# ---------------------------------------------------------------- files from tools/*_reviews_export.js
# {"format": "hapitech-reviews/1", "source": "google"|"facebook", "copied_at": iso, "summary": {...}, "reviews": [...]}
FB_REL = re.compile(r"^(\d+)\s*(y|mo|w|d|h|m)$")
MAX_PHOTOS = 8


def _fb_date(text, base):
    t = (text or "").strip()
    for fmt in ("%A %d %B %Y at %H:%M", "%A, %d %B %Y at %H:%M", "%d %B %Y at %H:%M", "%d %B %Y", "%B %d, %Y at %I:%M %p", "%A, %B %d, %Y at %I:%M %p"):
        try:
            return dt.datetime.strptime(t, fmt)
        except ValueError:
            pass
    m = FB_REL.match(t)
    if m:
        from utils.plans import add_months
        n, u = int(m.group(1)), m.group(2)
        d = (add_months(base, -12 * n) if u == "y" else add_months(base, -n) if u == "mo" else
             base - dt.timedelta(weeks=n) if u == "w" else base - dt.timedelta(days=n) if u == "d" else base)
        return dt.datetime.combine(d, dt.time(12))
    return None


def _fb_reply(item, page_names):
    """The business's own reply among a post's comments (first line of a comment is the commenter's name)."""
    for c in item.get("replies") or []:
        lines = [l.strip() for l in (c.get("text") or "").splitlines() if l.strip()]
        if not lines:
            continue
        who = lines[0]
        label = (c.get("label") or "")
        if not any(_norm(n) and (_norm(n) in _norm(who) or _norm(n) in _norm(label)) for n in page_names):
            continue
        body = [l for l in lines[1:] if l not in ("·", "Reply", "Like", "by author", "Author", "Top fan", "Edited")
                and not FB_REL.match(l) and not re.fullmatch(r"\d+", l) and l not in ("GIPHY",)]
        text = "\n".join(body).strip()
        if text:
            return text, _fb_date(c.get("time"), dt.date.today())
    return None, None


def _download_photos(account, urls):
    """Fetch review photos into the account's media (resized, metadata stripped). Returns media ids."""
    import io
    import urllib.request

    from models import db
    from models.content import Media
    from utils.uploads import UploadError, save_image

    class _F:
        def __init__(self, data):
            self.stream = io.BytesIO(data)
    ids = []
    for u in urls[:MAX_PHOTOS]:
        if not u.startswith("https://"):
            continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (HapiTech review import)"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                continue
            path, w, h = save_image(_F(data), account, prefix="review")
        except (UploadError, OSError, ValueError) as exc:
            print(f"[REVIEW_PHOTO] {u[:80]}: {exc}")
            continue
        m = Media(account_id=account.id, file_path=path, width=w, height=h, alt="Photo from a customer review")
        db.session.add(m)
        db.session.flush()
        ids.append(m.id)
    return ids


def import_file(account, data, photos=True, dry_run=False):
    """Add / update reviews from an export file. Safe to run as often as you like."""
    import json as _json

    from models import db
    from models.reviews import Review, ReviewReply
    if data.get("format") != "hapitech-reviews/1" or data.get("source") not in ("google", "facebook"):
        raise ValueError("That isn't a HapiTech review export. Use the Google or Facebook export script.")
    source = data["source"]
    try:
        copied = dt.datetime.fromisoformat(data["copied_at"].replace("Z", "+00:00")).date()
    except (KeyError, ValueError):
        copied = dt.date.today()
    existing = Review.query.filter_by(account_id=account.id, source=source).all()
    by_ext = {r.external_id: r for r in existing if r.external_id}
    by_name = {}
    for r in existing:
        by_name.setdefault(_norm(r.author_name), []).append(r)
    page_names = [account.name, data.get("business") or "", data.get("page") or ""]
    added, updated, skipped, photo_n = [], [], [], 0
    for pos, it in enumerate(data.get("reviews") or []):
        name = (it.get("author") or "").strip()
        if not name or len(name) > 120:
            skipped.append(name[:40] or "(no name)")
            continue
        ext = f"{source}:{it.get('id')}" if it.get("id") else None
        r = by_ext.get(ext)
        if r is None:                                     # first time with ids: link to a review copied in earlier
            cands = by_name.get(_norm(ALIASES.get(name.lower(), name))) or by_name.get(_norm(name)) or []
            cands = [c for c in cands if not (c.external_id or "").startswith(f"{source}:")]
            r = cands[0] if cands else None
        if source == "google":
            rating = it.get("rating") or (r.rating if r else 5)
            when = rel_date(it.get("date") or "", copied)
            when = dt.datetime.combine(when, dt.time(12)) if when else None
            text = (it.get("text") or "").strip()
            reply = (it.get("reply") or {}).get("text")
            rd = rel_date((it.get("reply") or {}).get("date") or "", copied)
            reply_at = dt.datetime.combine(rd, dt.time(12)) if rd else None
            recommends = None
        else:
            recommends = bool(it.get("recommends", True))
            rating = 5 if recommends else 1
            when = _fb_date(it.get("time"), copied)
            text = (it.get("text") or "").strip()
            reply, reply_at = _fb_reply(it, page_names)
        if r is None:
            r = Review(account_id=account.id, source=source, author_name=ALIASES.get(name.lower(), name)[:120],
                       rating=rating, body=text, status="published", verified=False)
            db.session.add(r)
            added.append(name)
        else:
            updated.append(name)
            if text and not (len(text) < len(r.body or "") and text.endswith("…")):
                r.body = text
            r.rating = rating
        r.external_id = ext or r.external_id
        r.recommends = recommends
        r.reviewed_at = when or r.reviewed_at
        r.sort_hint = pos
        r.price_tag = it.get("price") or r.price_tag
        urls = it.get("photos") or []
        r.photo_count = max(len(urls), r.photo_count or 0)
        if source == "google":
            r.source_url = account.google_reviews_url or r.source_url
        else:
            r.source_url = (it.get("id") if (it.get("id") or "").startswith("https://") else None) or account.facebook_url or r.source_url
        db.session.flush()
        if photos and urls and not dry_run:
            try:
                have = _json.loads(r.photos or "[]")
            except ValueError:
                have = []
            if not have:
                ids = _download_photos(account, urls)
                if ids:
                    r.photos = _json.dumps(ids)
                    photo_n += len(ids)
        if reply:
            rep = r.replies[-1] if r.replies else None
            if rep is None:
                rep = ReviewReply(review_id=r.id, body=reply)
                db.session.add(rep)
            rep.body = reply
            if reply_at:
                rep.created_at = reply_at
    s = data.get("summary") or {}
    if source == "google":
        if s.get("rating"):
            account.google_rating = s["rating"]
        if s.get("count"):
            account.google_count = s["count"]
    else:
        if s.get("recommend_pct") is not None:
            account.facebook_pct = s["recommend_pct"]
        if s.get("count"):
            account.facebook_count = s["count"]
        if data.get("url") and not account.facebook_url:
            account.facebook_url = data["url"].split("?")[0]
    account.reviews_synced_at = dt.datetime.utcnow()
    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return {"source": source, "in_file": len(data.get("reviews") or []), "added": added, "updated": updated,
            "skipped": skipped, "photos": photo_n, "summary": s}
