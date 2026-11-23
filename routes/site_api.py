# routes/site_api.py — read-only API for client websites (Roland's, Ray G).
# Auth: header `X-Site-Key: <key>` (created in Admin → client → Website tab; stored hashed).
# Client sites fetch server-side and cache for ~10 minutes, so their pages never depend on this
# being up at request time.
import json

from flask import Blueprint, abort, jsonify, request, url_for
from werkzeug.security import check_password_hash

from models import db
from models.content import ContentBlock, Media, Post
from models.core import Account
from models.reviews import Review
from utils.links import public_url

site_api_bp = Blueprint("site_api", __name__, url_prefix="/api/v1")


def _account(slug) -> Account:
    a = Account.query.filter_by(slug=slug, kind="client").first()
    key = request.headers.get("X-Site-Key", "")
    if not a or not a.site_api_key_hash or not key or not check_password_hash(a.site_api_key_hash, key):
        abort(401)
    return a


def _media_urls(ids, account_id):
    ids = [i for i in ids if isinstance(i, int)]
    if not ids:
        return []
    by_id = {m.id: m for m in Media.query.filter(Media.id.in_(ids), Media.account_id == account_id)}
    return [public_url(url_for("reviews_public.media_file", path=by_id[i].file_path)) for i in ids if i in by_id]


def _ok(payload):
    resp = jsonify({"ok": True, **payload})
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@site_api_bp.errorhandler(401)
def _unauth(e):
    return jsonify({"ok": False, "message": "Missing or wrong site key."}), 401


@site_api_bp.route("/sites/<slug>/reviews")
def reviews(slug):
    a = _account(slug)
    rows = (Review.query.filter(Review.account_id == a.id, Review.status.in_(["published", "reported"]))
            .order_by(Review.reviewed_at.desc().nullslast(), Review.sort_hint).all())
    out = []
    for r in rows:
        try:
            photo_ids = json.loads(r.photos or "[]")
        except ValueError:
            photo_ids = []
        out.append({
            "id": r.id, "name": r.author_name, "rating": r.rating, "text": r.body,
            "source": r.source, "source_label": r.source_label, "source_url": r.link,
            "verified": r.verified, "service": r.service, "town": r.town,
            "date": r.reviewed_at.date().isoformat() if r.reviewed_at else None,
            "photos": _media_urls(photo_ids, a.id),
            "reply": {"text": r.reply.body, "date": r.reply.created_at.date().isoformat()} if r.reply else None,
        })
    avg = round(sum(x["rating"] for x in out) / len(out), 2) if out else None
    return _ok({"business": a.name, "count": len(out), "average": avg, "reviews": out,
                "review_page": public_url(url_for("reviews_public.business", slug=a.slug)),
                "google_review_url": a.google_profile_url, "google_reviews_url": a.google_reviews_url})


@site_api_bp.route("/sites/<slug>/posts")
def posts(slug):
    a = _account(slug)
    rows = (Post.query.filter_by(account_id=a.id, status="published")
            .order_by(Post.published_at.desc()).limit(int(request.args.get("limit", 20))).all())
    return _ok({"posts": [{
        "id": p.id, "title": p.title, "text": p.body, "town": p.town,
        "date": p.published_at.date().isoformat() if p.published_at else None,
        "photos": _media_urls(p.photo_id_list, a.id),
    } for p in rows]})


@site_api_bp.route("/sites/<slug>/content")
def content(slug):
    """Editable blocks. Images come back as {"static": "img/x.jpg"} (a file the site already has)
    or {"url": "https://hapitech.dev/media/..."} (a photo the client uploaded)."""
    a = _account(slug)
    blocks = ContentBlock.query.filter_by(account_id=a.id).all()
    out = {}
    for b in blocks:
        v = b.data
        if b.type == "setting":
            continue                      # hero settings: sent below as "hero"
        if b.type == "images" and b.value == b.default_value:
            continue                      # unedited photos: the site keeps using its own folder, unchanged
        if b.type == "images":
            imgs = []
            for x in v or []:
                if isinstance(x, str) and x.startswith("static:"):
                    imgs.append({"static": x[len("static:"):]})
                else:
                    urls = _media_urls([x], a.id)
                    if urls:
                        imgs.append({"url": urls[0]})
            v = imgs
        out[b.key] = v
    updated = max((b.updated_at for b in blocks), default=None)
    away = {"until": a.away_until.isoformat(), "message": a.away_message} if a.is_away else None
    from utils.photos import hero_pool, likes_map
    return _ok({"content": out, "away": away, "likes": likes_map(a), "hero": hero_pool(a),
                "updated": updated.isoformat() if updated else None})


@site_api_bp.route("/sites/<slug>/likes", methods=["POST"])
def photo_like(slug):
    """♥ from a visitor, relayed by the client site's server: {"photo": "<site photo key>", "delta": 1 | -1}."""
    from utils.photos import like
    a = _account(slug)
    d = request.get_json(silent=True) or {}
    count = like(a, str(d.get("photo") or "")[:400], int(d.get("delta") or 1))
    if count is None:
        return jsonify({"ok": False, "message": "Unknown photo."}), 404
    return jsonify({"ok": True, "count": count})


ENQUIRIES_PER_DAY = 60          # per site, a ceiling against a broken or abused form


@site_api_bp.route("/sites/<slug>/enquiries", methods=["POST"])
def enquiry(slug):
    """The client site's quote / booking forms send a copy here, so it lands in their Jobs list.
    (The site keeps emailing the owner as it always has.)"""
    import datetime as dt

    from flask import jsonify

    from models.work import Lead
    a = _account(slug)
    since = dt.datetime.utcnow() - dt.timedelta(days=1)
    if Lead.query.filter(Lead.account_id == a.id, Lead.source.in_(["website", "booking"]),
                         Lead.created_at >= since).count() >= ENQUIRIES_PER_DAY:
        return jsonify({"ok": False, "message": "Daily limit reached."}), 429
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()[:120]
    if not name:
        return jsonify({"ok": False, "message": "Name required."}), 400
    source = "booking" if d.get("source") == "booking" else "website"
    lead = Lead(account_id=a.id, source=source, name=name, email=(d.get("email") or "").strip()[:255] or None,
                phone=(d.get("phone") or "").strip()[:40] or None,
                postcode=(d.get("postcode") or "").strip().upper()[:12] or None,
                title=(d.get("job") or "").strip()[:160] or None, message=(d.get("message") or "").strip()[:5000] or None,
                preferred=(d.get("preferred") or "").strip()[:200] or None,
                travel_note=(d.get("travel_note") or "").strip()[:200] or None)
    db.session.add(lead)
    db.session.commit()
    if source == "booking" and a.contact_email:
        from utils.mailer import send_email
        try:
            from utils import email_html
            email_html.send(a.contact_email, f"New booking request from {name}", heading="New booking request",
                            lines=[f"{name} would like to book in with you."],
                            box=[("Job", lead.title or (lead.message or "")[:120] or "—"),
                                 ("Preferred", lead.preferred or "Any time"), ("Postcode", lead.postcode or "—")],
                            button={"label": "Confirm it in your dashboard",
                                    "url": public_url(url_for("portal.job", lid=lead.id))})
        except Exception as exc:
            print(f"[BOOKING_NOTIFY] {exc}")
    return jsonify({"ok": True, "id": lead.id}), 201


PHOTO_BLOCKS = {
    "hero": ("Top-of-page photos", 60, "The big photo at the top of your homepage. One is picked each visit."),
    "gallery": ("Gallery photos", 80, "Your work gallery. The first five show on the homepage strip."),
    "photos": ("Your photos", 80, "Used at the top of your homepage and in your gallery."),
}


@site_api_bp.route("/sites/<slug>/defaults", methods=["POST"])
def defaults(slug):
    """The site reports its own photo lists on start-up. They become the editable defaults,
    so the dashboard shows exactly what's on the site until the client changes something."""
    import json as _json
    a = _account(slug)
    d = request.get_json(silent=True) or {}
    photos = d.get("photos") or {}
    updated = []
    for key, paths in photos.items():
        if key not in PHOTO_BLOCKS or not isinstance(paths, list):
            continue
        clean = [f"static:{p}" for p in paths[:200] if isinstance(p, str) and p.startswith("img/") and ".." not in p]
        label, limit, help_text = PHOTO_BLOCKS[key]
        new_default = _json.dumps(clean)
        b = ContentBlock.query.filter_by(account_id=a.id, key=f"photos.{key}").first()
        if b is None:
            b = ContentBlock(account_id=a.id, key=f"photos.{key}", value=new_default)
            db.session.add(b)
        elif b.value == b.default_value:          # not edited yet: follow the site's folder
            b.value = new_default
        b.type, b.label, b.group, b.help, b.max_length = "images", label, "Photos", help_text, limit
        b.default_value = new_default
        updated.append(key)
    db.session.commit()
    return jsonify({"ok": True, "updated": updated})


@site_api_bp.route("/sites/<slug>/visits", methods=["POST"])
def visits(slug):
    """Batched page counts from the site's server: {"hits": [{"day","path","ref","n"}]}."""
    import datetime as _dt

    from models.content import SiteVisit
    a = _account(slug)
    hits = (request.get_json(silent=True) or {}).get("hits") or []
    today = _dt.date.today()
    for h in hits[:500]:
        try:
            day = _dt.date.fromisoformat(h.get("day"))
            n = max(0, min(int(h.get("n") or 0), 100000))
        except (TypeError, ValueError):
            continue
        if n == 0 or abs((today - day).days) > 2:
            continue
        path, ref = str(h.get("path") or "/")[:200], str(h.get("ref") or "")[:100]
        row = SiteVisit.query.filter_by(account_id=a.id, day=day, path=path, ref=ref).first()
        if row is None:
            row = SiteVisit(account_id=a.id, day=day, path=path, ref=ref, count=0)
            db.session.add(row)
        row.count += n
    db.session.commit()
    return jsonify({"ok": True})
