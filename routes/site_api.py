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
            "source": r.source, "source_label": r.source_label, "source_url": r.source_url,
            "verified": r.verified, "service": r.service, "town": r.town,
            "date": r.reviewed_at.date().isoformat() if r.reviewed_at else None,
            "photos": _media_urls(photo_ids, a.id),
            "reply": {"text": r.reply.body, "date": r.reply.created_at.date().isoformat()} if r.reply else None,
        })
    avg = round(sum(x["rating"] for x in out) / len(out), 2) if out else None
    return _ok({"business": a.name, "count": len(out), "average": avg, "reviews": out,
                "review_page": public_url(url_for("reviews_public.business", slug=a.slug)),
                "google_review_url": a.google_profile_url})


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
    return _ok({"content": out, "away": away, "updated": updated.isoformat() if updated else None})


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
            send_email(to=a.contact_email, subject=f"Booking request from {name}",
                       text=f"{name} would like to book: {lead.title or lead.message or ''}\n"
                            f"Preferred: {lead.preferred or 'any time'}\nPostcode: {lead.postcode or '—'}\n\n"
                            f"Confirm it in your dashboard: Jobs.")
        except Exception as exc:
            print(f"[BOOKING_NOTIFY] {exc}")
    return jsonify({"ok": True, "id": lead.id}), 201
