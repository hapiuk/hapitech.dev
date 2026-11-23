# routes/admin/reviews.py — every client's reviews in one place: moderation + manual imports.
import datetime as dt

from flask import abort, flash, redirect, render_template, request, url_for

from models import db
from models.core import Account
from models.reviews import REVIEW_SOURCES, Review
from utils.security import safe_next

from . import admin_bp


@admin_bp.route("/reviews")
def reviews():
    status = request.args.get("status", "reported")
    acct = request.args.get("client")
    q = Review.query
    if status != "all":
        q = q.filter_by(status=status)
    if acct:
        a = Account.query.filter_by(slug=acct).first()
        q = q.filter_by(account_id=a.id if a else -1)
    from utils import review_search
    q, active = review_search.apply(q, request.args)
    total = q.count()
    rows = q.limit(300).all()
    counts = dict(db.session.query(Review.status, db.func.count()).group_by(Review.status).all())
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    return render_template("admin/reviews.html", rows=rows, status=status, counts=counts, clients=clients,
                           client=acct, sources=REVIEW_SOURCES, today=dt.date.today(),
                           undated=sum(1 for r in rows if not r.reviewed_at), total=total, active=active)


@admin_bp.route("/reviews/<int:rid>", methods=["POST"])
def review_set(rid):
    r = db.session.get(Review, rid) or abort(404)
    action = request.form.get("action")
    if action == "date":
        try:
            v = request.form.get("reviewed_at")
            r.reviewed_at = dt.datetime.fromisoformat(v) if v else None
            flash("Date saved." if v else "Date cleared.", "ok")
        except ValueError:
            flash("That date didn't look right.", "err")
    elif action == "publish":
        r.status, r.report_reason = "published", None
        flash("Review is showing again.", "ok")
    elif action == "remove":
        r.status = "removed"
        flash("Review removed from public view (kept on record).", "ok")
    db.session.commit()
    return redirect(safe_next(request.form.get("back")) or url_for("admin.reviews"))


@admin_bp.route("/reviews/new", methods=["GET", "POST"])
def review_new():
    """Add a review by hand, e.g. from a Google / Checkatrade screenshot the client sent."""
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    if request.method == "POST":
        f = request.form
        a = Account.query.filter_by(slug=f.get("client")).first()
        try:
            rating = int(f.get("rating") or 0)
        except ValueError:
            rating = 0
        if not a or not (1 <= rating <= 5) or not (f.get("author_name") or "").strip():
            flash("Choose a client, a rating of 1–5 and the reviewer's name.", "err")
            return render_template("admin/review_form.html", clients=clients, f=f, sources=REVIEW_SOURCES)
        when = f.get("reviewed_at")
        r = Review(account_id=a.id, source=f.get("source") if f.get("source") in REVIEW_SOURCES else "manual",
                   source_url=(f.get("source_url") or "").strip() or (a.google_profile_url if f.get("source") == "google" else None),
                   author_name=f["author_name"].strip()[:120], rating=rating, body=(f.get("body") or "").strip(),
                   service=(f.get("service") or "").strip() or None, town=(f.get("town") or "").strip() or None,
                   reviewed_at=dt.datetime.fromisoformat(when) if when else None,
                   status="published", verified=False)
        db.session.add(r)
        db.session.commit()
        flash(f"Review added to {a.name}.", "ok")
        return redirect(url_for("admin.client", slug=a.slug, tab="reviews"))
    return render_template("admin/review_form.html", clients=clients, f={"client": request.args.get("client"),
                                                                          "source": "google"},
                           sources=REVIEW_SOURCES)



@admin_bp.route("/reviews/import", methods=["GET", "POST"])
def reviews_import():
    """Upload a file from tools/google_reviews_export.js or tools/facebook_reviews_export.js."""
    import json
    import os

    from flask import current_app
    from utils.review_import import import_file
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    result, error = None, None
    if request.method == "POST":
        a = Account.query.filter_by(slug=request.form.get("client")).first()
        up = request.files.get("file")
        if not a or not up or not up.filename:
            error = "Choose the business and the file."
        else:
            try:
                data = json.load(up.stream)
                result = import_file(a, data, photos=bool(request.form.get("photos")), dry_run=bool(request.form.get("dry")))
                result["client"] = a
                result["dry"] = bool(request.form.get("dry"))
            except (ValueError, UnicodeDecodeError) as exc:
                error = str(exc) if "HapiTech" in str(exc) else f"Couldn't read that file: {exc}"
    base = request.url_root.rstrip("/")
    scripts = {key: f"window.__HT_BASE={base!r};\n" + _script(key) for key in ("google", "facebook")}
    return render_template("admin/reviews_import.html", clients=clients, result=result, error=error, scripts=scripts,
                           bookmarklet=bookmarklet(),
                           chosen=request.form.get("client") or request.args.get("client"))



def _script(key):
    import os

    from flask import current_app
    try:
        with open(os.path.join(current_app.root_path, "tools", f"{key}_reviews_export.js"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def bookmarklet():
    """One bookmark for both sites: runs the Google or Facebook export depending on the page, then offers
    "Send to HapiTech" (back to this site)."""
    from urllib.parse import quote
    base = request.url_root.rstrip("/")
    code = (f"window.__HT_BASE={base!r};if(/facebook\\.com$/.test(location.hostname)){{{_script('facebook')}}}"
            f"else if(/google\\./.test(location.hostname)){{{_script('google')}}}"
            "else{alert('Open the business on Google Maps (Reviews tab) or its Facebook Reviews page first.')}")
    return "javascript:" + quote("(function(){" + code + "})()", safe="")


def _guess_client(data):
    import re as _re
    norm = lambda s: _re.sub(r"[^a-z0-9]", "", (s or "").lower())
    keys = [norm(data.get("business")), norm(data.get("page")), norm((data.get("url") or "").split("?")[0])]
    best, score = None, 0
    for a in Account.query.filter_by(kind="client").all():
        cands = [norm(a.name), norm(a.facebook_url), norm((a.google_maps_url or "").split("/@")[0]), norm(a.slug)]
        for k in keys:
            for c in cands:
                if k and c and (k in c or c in k):
                    s = min(len(k), len(c))
                    if s > score:
                        best, score = a, s
    return best


@admin_bp.route("/reviews/receive")
def reviews_receive():
    """Opened by "Send to HapiTech" on a Google / Facebook page; receives the reviews from that tab."""
    clients = Account.query.filter_by(kind="client").order_by(Account.name).all()
    return render_template("admin/reviews_receive.html", clients=clients)


@admin_bp.route("/reviews/import-json", methods=["POST"])
def reviews_import_json():
    from flask import jsonify
    from utils.review_import import import_file
    body = request.get_json(silent=True) or {}
    data = body.get("data") or {}
    a = Account.query.filter_by(slug=body.get("client")).first() if body.get("client") else _guess_client(data)
    if not a:
        return jsonify({"ok": False, "message": "Couldn't tell which business this is. Choose it below."})
    try:
        res = import_file(a, data, photos=not body.get("dry"), dry_run=bool(body.get("dry")))
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    return jsonify({"ok": True, "client": a.slug, "client_name": a.name, "dry": bool(body.get("dry")),
                    "source": res["source"], "in_file": res["in_file"], "added": res["added"], "updated": len(res["updated"]),
                    "skipped": len(res["skipped"]), "photos": res["photos"], "summary": res["summary"],
                    "page": url_for("hub.business", slug=a.slug), "reviews": url_for("admin.client", slug=a.slug, tab="reviews")})
