# utils/content_blocks.py — editable content blocks for client sites.
# ensure_blocks() registers a site's blocks with its current hard-coded text as the default,
# so switching a site over to the API changes nothing visible until the client edits something.
import json

from models import db
from models.content import ContentBlock, Media


class BlockError(ValueError):
    pass


def ensure_blocks(account, site_dir) -> int:
    """Register the editable blocks for a client site. Definitions live in utils/site_blocks.py."""
    try:
        from utils.site_blocks import definitions_for
    except ImportError:
        return 0
    created = 0
    for i, d in enumerate(definitions_for(account, site_dir)):
        b = ContentBlock.query.filter_by(account_id=account.id, key=d["key"]).first()
        default = json.dumps(d["default"], ensure_ascii=False)
        if b is None:
            b = ContentBlock(account_id=account.id, key=d["key"], value=default)
            db.session.add(b)
            created += 1
        elif b.value == b.default_value and b.default_value != default:
            b.value = default             # never edited: follow the site's updated wording (e.g. a refreshed policy)
        b.type, b.label, b.group = d["type"], d["label"], d.get("group", "General")
        b.help, b.max_length, b.sort = d.get("help"), d.get("max_length"), d.get("sort", i)
        b.default_value = default
    db.session.flush()
    return created


def parse_block_form(block, form, files, account, user) -> str:
    """Turn the submitted edit form into the block's JSON value, enforcing type + length rules."""
    t, limit = block.type, block.max_length
    if t in ("text", "longtext", "price", "page"):
        v = (form.get("value") or "").strip()
        if not v:
            raise BlockError("This can't be empty. Use \"Back to original\" to restore the old text.")
        if limit and len(v) > limit:
            raise BlockError(f"Please keep this under {limit} characters (it's {len(v)}).")
        if t == "text" and "\n" in v:
            v = " ".join(v.split())
        return json.dumps(v, ensure_ascii=False)
    if t == "list":
        items = [ln.strip() for ln in (form.get("value") or "").splitlines() if ln.strip()]
        if not items:
            raise BlockError("Add at least one line.")
        if limit and len(items) > limit:
            raise BlockError(f"Up to {limit} lines, please.")
        return json.dumps(items, ensure_ascii=False)
    if t == "hours":
        days = form.getlist("day")
        texts = form.getlist("hours")
        rows = [[d.strip()[:20], h.strip()[:40]] for d, h in zip(days, texts) if d.strip()]
        return json.dumps(rows, ensure_ascii=False)
    if t == "images":
        from utils.uploads import UploadError, save_image
        current = block.data or []
        keep = set(form.getlist("keep"))
        out = [x for x in current if str(x) in keep]
        for up in files.getlist("photos"):
            if not up or not up.filename:
                continue
            if limit and len(out) >= limit:
                raise BlockError(f"Up to {limit} photos here.")
            try:
                path, w, h = save_image(up, account, prefix="site")
            except UploadError as e:
                raise BlockError(str(e))
            m = Media(account_id=account.id, file_path=path, width=w, height=h, uploaded_by=user.id)
            db.session.add(m)
            db.session.flush()
            out.append(m.id)
        order = form.get("order")
        if order:
            pos = {k: i for i, k in enumerate(order.split(","))}
            out.sort(key=lambda x: pos.get(str(x), 999))
        if not out:
            raise BlockError("Keep at least one photo.")
        return json.dumps(out)
    raise BlockError("This kind of content can't be edited here yet.")
