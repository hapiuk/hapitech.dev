# utils/photos.py — a client site's photos as the site itself names them, ♥ likes, and the hero choice.
#
# Photo keys are what the client site uses: "img/gallery/x.jpg" (a file in the site's own static folder)
# or "url:https://hapitech.dev/media/…" (a photo uploaded through the dashboard).
#
# Hero ("top-of-page photo") modes, stored as content blocks hero.mode / hero.pick:
#   all    – random from all the site's photos (the original behaviour; default)
#   liked  – random from the most-liked photos (falls back to "all" until something has a like)
#   chosen – random from photos the client ticked (falls back to "all" if none ticked)
import json

from flask import url_for

from models import db
from models.content import ContentBlock, ContentBlockVersion, Media, PhotoLike
from utils.links import public_url

HERO_MODES = {"all": "Random from all my photos", "liked": "Random from my most-liked photos",
              "chosen": "Random from photos I choose"}
TOP_LIKED = 8


def _block_keys(account, b):
    out = []
    for x in b.data or []:
        if isinstance(x, str) and x.startswith("static:"):
            out.append(x[len("static:"):])
        elif isinstance(x, int):
            m = db.session.get(Media, x)
            if m and m.account_id == account.id:
                out.append("url:" + public_url(url_for("reviews_public.media_file", path=m.file_path)))
    return out


def known_photos(account) -> list:
    """Every photo currently on the site's hero/gallery lists, in order, without duplicates."""
    keys = []
    for b in ContentBlock.query.filter(ContentBlock.account_id == account.id, ContentBlock.key.like("photos.%")) \
            .order_by(ContentBlock.key).all():
        for k in _block_keys(account, b):
            if k not in keys:
                keys.append(k)
    return keys


def photo_src(account, key) -> str:
    """Where the dashboard can show a thumbnail of this photo."""
    return key[4:] if key.startswith("url:") else f"https://{account.domain}/static/{key}"


def like(account, photo, delta) -> int | None:
    if photo not in known_photos(account):
        return None
    row = PhotoLike.query.filter_by(account_id=account.id, photo=photo).first()
    if row is None:
        row = PhotoLike(account_id=account.id, photo=photo, count=0)
        db.session.add(row)
    row.count = max(0, row.count + (1 if delta > 0 else -1))
    db.session.commit()
    return row.count


def likes_map(account) -> dict:
    return {r.photo: r.count for r in PhotoLike.query.filter_by(account_id=account.id).all() if r.count}


def _setting(account, key, default):
    b = ContentBlock.query.filter_by(account_id=account.id, key=key).first()
    return b.data if b else default


def hero_mode(account) -> str:
    m = _setting(account, "hero.mode", "all")
    return m if m in HERO_MODES else "all"


def hero_pick(account) -> list:
    return [k for k in (_setting(account, "hero.pick", []) or []) if isinstance(k, str)]


def save_hero(account, mode, pick, user_id=None):
    for key, value, label in (("hero.mode", mode if mode in HERO_MODES else "all", "Top-of-page photo: mode"),
                              ("hero.pick", [k for k in pick if k in known_photos(account)], "Top-of-page photo: chosen")):
        b = ContentBlock.query.filter_by(account_id=account.id, key=key).first()
        if b is None:
            b = ContentBlock(account_id=account.id, key=key, type="setting", label=label, group="_hero",
                             default_value=json.dumps("all" if key == "hero.mode" else []))
            db.session.add(b)
        b.value, b.updated_by = json.dumps(value), user_id
    db.session.commit()


def hero_pool(account):
    """The photos the site should pick its hero from, or None for "use your own random choice"."""
    mode = hero_mode(account)
    if mode == "chosen":
        return hero_pick(account) or None
    if mode == "liked":
        known = set(known_photos(account))
        top = sorted(((c, p) for p, c in likes_map(account).items() if p in known), reverse=True)[:TOP_LIKED]
        return [p for _, p in top] or None
    return None


# ---------------------------------------------------------------- post photos -> website gallery

GALLERY_KEYS = ("photos.gallery", "photos.photos")      # Roland: photos.gallery, Ray: photos.photos


def gallery_block(account):
    for key in GALLERY_KEYS:
        b = ContentBlock.query.filter_by(account_id=account.id, key=key, type="images").first()
        if b:
            return b
    return None


def add_to_gallery(account, media_ids, user_id=None) -> int:
    """Put a post's photos at the front of the site's gallery (newest work first). Returns how many were added."""
    b = gallery_block(account)
    if not b or not media_ids:
        return 0
    current = b.data if isinstance(b.data, list) else []
    new = [i for i in media_ids if i not in current]
    if not new:
        return 0
    db.session.add(ContentBlockVersion(block_id=b.id, value=b.value, saved_by=user_id))
    b.value, b.updated_by = json.dumps(new + current), user_id
    return len(new)


def remove_from_gallery(account, media_ids, user_id=None):
    """Called before a post's photos are deleted, so the gallery never points at a missing file."""
    b = gallery_block(account)
    if not b or not media_ids:
        return
    current = b.data if isinstance(b.data, list) else []
    kept = [x for x in current if x not in set(media_ids)]
    if kept != current:
        b.value, b.updated_by = json.dumps(kept), user_id
        for v in b.versions:            # undo history must not bring a deleted photo back either
            try:
                old = json.loads(v.value)
            except ValueError:
                continue
            if isinstance(old, list):
                v.value = json.dumps([x for x in old if x not in set(media_ids)])
