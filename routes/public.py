# routes/public.py — public marketing pages and the contact form.
import datetime

from flask import Blueprint, jsonify, redirect, render_template, request
from flask_login import current_user

from utils.mailer import send_contact_email

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    from utils.news import get_news
    # never block the homepage on feeds: empty list (section hidden) until a cache exists
    news_items, seen = [], set()
    for item in get_news(blocking=False).get("items", []):   # newest first, one per source
        if item.get("source_id") not in seen:
            seen.add(item.get("source_id"))
            news_items.append(item)
        if len(news_items) == 3:
            break
    return render_template("home.html", news_items=news_items)


@public_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@public_bp.route("/terms")
def terms():
    return render_template("terms.html")


@public_bp.route("/contact", methods=["POST"])
def contact():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:120]
    email = (data.get("email") or "").strip()[:255]
    message = (data.get("message") or "").strip()[:5000]
    if not (name and email and message):
        return jsonify({"success": False, "message": "All fields required"}), 400
    meta = {
        "client": (data.get("client") or "").strip()[:80],
        "host": request.host,
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "ua": request.headers.get("User-Agent", ""),
        "referer": request.headers.get("Referer", ""),
        "utc": datetime.datetime.utcnow().isoformat(),
    }
    try:
        send_contact_email(name=name, email=email, message=message, meta=meta)
    except Exception as e:
        print(f"[CONTACT_EMAIL_ERROR] {e}")
        return jsonify({"success": False, "message": "Could not send right now. Try again shortly."}), 500
    return jsonify({"success": True, "message": "Sent — we’ll get back to you shortly."})
