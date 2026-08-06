import os
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, current_app
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy import func

from models import db
from models.solar_user import SolarUser, SolarLoginCode, SolarJournalEntry
from utils.mailer import send_login_code_email
from utils.body_facts import get_body_facts
from utils.body_stats import get_body_stats
from utils.solar_journal_limits import (
    process_image,
    UploadError,
    UploadTooLargeError,
    PER_BODY_ENTRY_CAP,
    GLOBAL_SOFT_CEILING_BYTES,
)

solar_system_bp = Blueprint(
    "solar_system",
    __name__,
    url_prefix="/solar-system"
)

EARLY_SUPPORTER_LIMIT = 100
RESEND_COOLDOWN_SECONDS = 30


def _is_solar_user() -> bool:
    return current_user.is_authenticated and isinstance(current_user, SolarUser)


def _is_owner() -> bool:
    """The old single-owner journal (Aaron's own) — admin/client login only,
    completely separate from the public SolarUser accounts."""
    return current_user.is_authenticated and getattr(current_user, "role", None) in ("admin", "client")


def _load_body_choices():
    import json
    path = os.path.join(current_app.static_folder, "solar-system", "data", "bodies.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return []

    choices = []
    for b in data.get("bodies", []):
        if b.get("name"):
            choices.append({"kind": "planet", "name": b["name"], "label": b["name"]})
    for m in data.get("moons", []):
        if m.get("name"):
            label = f"{m['name']} ({m['parent']})" if m.get("parent") else m["name"]
            choices.append({"kind": "moon", "name": m["name"], "label": label})
    return choices


def _issue_code(email: str, pending_display_name: str = None):
    """Invalidate any outstanding code for this email and issue a fresh one.
    Returns the SolarLoginCode row, or None if a recent one is still live
    (caller should tell the user to check their email instead of resending).
    """
    recent = (
        SolarLoginCode.query
        .filter_by(email=email, consumed=False)
        .order_by(SolarLoginCode.created_at.desc())
        .first()
    )

    if recent and not recent.is_expired:
        age = (datetime.utcnow() - recent.created_at).total_seconds()
        if age < RESEND_COOLDOWN_SECONDS:
            return None

    # Invalidate any other still-live codes for this email.
    SolarLoginCode.query.filter_by(email=email, consumed=False).update({"consumed": True})
    db.session.commit()

    raw_code = SolarLoginCode.generate_code()
    entry = SolarLoginCode(email=email, pending_display_name=pending_display_name)
    entry.set_code(raw_code)

    # Send first — only persist the code once we know it actually went out,
    # so a failed send doesn't leave a phantom code blocking the resend cooldown.
    send_login_code_email(email=email, code=raw_code)

    db.session.add(entry)
    db.session.commit()

    return entry


# =========================
# PAGES
# =========================

@solar_system_bp.route("/")
def index():
    app_js_path = os.path.join(current_app.static_folder, "solar-system", "app.js")
    try:
        app_js_version = str(int(os.path.getmtime(app_js_path)))
    except OSError:
        app_js_version = "0"

    return render_template(
        "solar_system/index.html",
        is_solar_user=_is_solar_user(),
        display_name=current_user.display_name if _is_solar_user() else None,
        show_owner_journal=_is_owner(),
        app_js_version=app_js_version
    )


@solar_system_bp.route("/api/objects")
def api_objects():
    return jsonify([])


@solar_system_bp.route("/register")
def register():
    if _is_solar_user():
        return redirect(url_for("solar_system.journal"))
    return render_template("solar_system/register.html")


@solar_system_bp.route("/login")
def login():
    if _is_solar_user():
        return redirect(url_for("solar_system.journal"))
    return render_template("solar_system/login.html")


@solar_system_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("solar_system.index"))


@solar_system_bp.route("/journal")
@login_required
def journal():
    if not _is_solar_user():
        return redirect(url_for("solar_system.index"))
    return render_template("solar_system/journal.html", body_choices=_load_body_choices())


@solar_system_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if not _is_solar_user():
        return redirect(url_for("solar_system.index"))

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        new_display_name = (data.get("display_name") or "").strip()

        if not new_display_name:
            return jsonify({"success": False, "message": "Display name cannot be empty"}), 400

        current_user.display_name = new_display_name
        db.session.commit()
        return jsonify({"success": True, "message": "Profile updated"})

    return render_template("solar_system/profile.html")


# =========================
# PASSWORDLESS AUTH API
# =========================

@solar_system_bp.route("/auth/request-register-code", methods=["POST"])
def request_register_code():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    display_name = (data.get("display_name") or "").strip()

    if not email or not display_name:
        return jsonify({"success": False, "message": "Email and display name are required."}), 400

    if SolarUser.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "An account already exists for that email — try logging in instead."}), 409

    try:
        entry = _issue_code(email, pending_display_name=display_name)
    except Exception as e:
        print(f"[SOLAR AUTH] Failed to send registration code to {email}: {e}")
        return jsonify({"success": False, "message": "Could not send the code email right now. Please try again shortly."}), 500

    if entry is None:
        return jsonify({"success": True, "message": "A code was already sent — check your email."})

    return jsonify({"success": True, "message": "Code sent — check your email."})


@solar_system_bp.route("/auth/request-login-code", methods=["POST"])
def request_login_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    if not SolarUser.query.filter_by(email=email).first():
        return jsonify({"success": False, "message": "No account found for that email — try creating one instead."}), 404

    try:
        entry = _issue_code(email)
    except Exception as e:
        print(f"[SOLAR AUTH] Failed to send login code to {email}: {e}")
        return jsonify({"success": False, "message": "Could not send the code email right now. Please try again shortly."}), 500

    if entry is None:
        return jsonify({"success": True, "message": "A code was already sent — check your email."})

    return jsonify({"success": True, "message": "Code sent — check your email."})


@solar_system_bp.route("/auth/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    if not email or not code:
        return jsonify({"success": False, "message": "Email and code are required."}), 400

    entry = (
        SolarLoginCode.query
        .filter_by(email=email, consumed=False)
        .order_by(SolarLoginCode.created_at.desc())
        .first()
    )

    if entry is None:
        return jsonify({"success": False, "message": "No active code for that email. Request a new one."}), 400

    if entry.is_expired:
        return jsonify({"success": False, "message": "That code has expired. Request a new one."}), 400

    if entry.is_locked_out:
        return jsonify({"success": False, "message": "Too many incorrect attempts. Request a new code."}), 429

    if not entry.check_code(code):
        entry.attempts += 1
        db.session.commit()
        return jsonify({"success": False, "message": "Incorrect code."}), 401

    entry.consumed = True
    db.session.commit()

    user = SolarUser.query.filter_by(email=email).first()

    is_new_account = user is None
    if is_new_account:
        existing_count = SolarUser.query.filter_by(is_early_supporter=True).count()
        user = SolarUser(
            email=email,
            display_name=entry.pending_display_name or email.split("@")[0],
            is_early_supporter=existing_count < EARLY_SUPPORTER_LIMIT
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)

    return jsonify({
        "success": True,
        "message": "Logged in",
        "is_new_account": is_new_account,
        "is_early_supporter": user.is_early_supporter
    })


# =========================
# JOURNAL ENTRIES (personal, per-account)
# =========================

def _upload_dir_for(user_id: int) -> str:
    path = os.path.join(current_app.static_folder, "uploads", "solar_journal", str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _entry_to_dict(entry: SolarJournalEntry, include_author=False) -> dict:
    image_url = None
    if entry.image_filename:
        image_url = url_for(
            "static",
            filename=f"uploads/solar_journal/{entry.user_id}/{entry.image_filename}"
        )
    d = {
        "id": entry.id,
        "title": entry.title,
        "body": entry.body,
        "entity_kind": entry.entity_kind,
        "entity_name": entry.entity_name,
        "is_public": entry.is_public,
        "image_url": image_url,
        "created_at": entry.created_at.isoformat()
    }
    if include_author:
        d["author"] = entry.user.display_name if entry.user else "Someone"
    return d


@solar_system_bp.route("/journal/entries", methods=["GET"])
@login_required
def journal_entries_list():
    if not _is_solar_user():
        return jsonify({"success": False, "message": "Not authorized."}), 403

    query = SolarJournalEntry.query.filter_by(user_id=current_user.id)

    entity_name = request.args.get("entity_name")
    if entity_name:
        query = query.filter_by(entity_name=entity_name)

    entries = query.order_by(SolarJournalEntry.created_at.desc()).all()
    return jsonify({"success": True, "entries": [_entry_to_dict(e) for e in entries]})


@solar_system_bp.route("/journal/entries", methods=["POST"])
@login_required
def journal_entries_create():
    if not _is_solar_user():
        return jsonify({"success": False, "message": "Not authorized."}), 403

    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    image_file = request.files.get("image")
    entity_kind = (request.form.get("entity_kind") or "general").strip().lower()
    entity_name = (request.form.get("entity_name") or "General").strip()
    is_public = (request.form.get("is_public") or "").lower() in ("1", "true", "on", "yes")

    if entity_kind not in ("planet", "moon", "general"):
        entity_kind = "general"
    if entity_kind == "general":
        entity_name = "General"

    if not title:
        return jsonify({"success": False, "message": "Please give your entry a title."}), 400

    # Per-body cap — 2 entries total per user per body, any mix of personal/public.
    current_count = SolarJournalEntry.query.filter_by(user_id=current_user.id, entity_name=entity_name).count()
    if current_count >= PER_BODY_ENTRY_CAP:
        return jsonify({
            "success": False,
            "message": f"You've reached the {PER_BODY_ENTRY_CAP}-entry limit for {entity_name}. Delete an existing entry for this body to add a new one."
        }), 409

    image_filename = None
    image_size_bytes = None

    if image_file and image_file.filename:
        # Global ceiling only matters when an image is actually being added —
        # a text-only entry is negligible.
        current_total = db.session.query(
            func.coalesce(func.sum(SolarJournalEntry.image_size_bytes), 0)
        ).scalar()

        if current_total >= GLOBAL_SOFT_CEILING_BYTES:
            return jsonify({
                "success": False,
                "message": "Storage is full right now — please try again later or contact support."
            }), 507

        try:
            jpeg_bytes, size = process_image(image_file)
        except UploadTooLargeError as e:
            return jsonify({"success": False, "message": str(e)}), 413
        except UploadError as e:
            return jsonify({"success": False, "message": str(e)}), 400

        if current_total + size > GLOBAL_SOFT_CEILING_BYTES:
            return jsonify({
                "success": False,
                "message": "That upload would put us over our storage limit — please try a smaller image."
            }), 507

        image_filename = f"{uuid.uuid4().hex}.jpg"
        image_size_bytes = size

        dest_path = os.path.join(_upload_dir_for(current_user.id), image_filename)
        with open(dest_path, "wb") as f:
            f.write(jpeg_bytes)

    entry = SolarJournalEntry(
        user_id=current_user.id,
        title=title,
        body=body or None,
        entity_kind=entity_kind,
        entity_name=entity_name,
        is_public=is_public,
        image_filename=image_filename,
        image_size_bytes=image_size_bytes
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({"success": True, "entry": _entry_to_dict(entry)})


@solar_system_bp.route("/journal/entries/<int:entry_id>", methods=["DELETE"])
@login_required
def journal_entries_delete(entry_id):
    if not _is_solar_user():
        return jsonify({"success": False, "message": "Not authorized."}), 403

    entry = SolarJournalEntry.query.filter_by(id=entry_id, user_id=current_user.id).first()
    if not entry:
        return jsonify({"success": False, "message": "Entry not found."}), 404

    if entry.image_filename:
        image_path = os.path.join(_upload_dir_for(current_user.id), entry.image_filename)
        if os.path.exists(image_path):
            os.remove(image_path)

    db.session.delete(entry)
    db.session.commit()

    return jsonify({"success": True, "message": "Deleted."})


# =========================
# PUBLIC INFO PANEL (body facts + community entries)
# Deliberately not login-gated — this is meant to be browsable by anyone.
# =========================

@solar_system_bp.route("/api/body-info")
def body_info():
    name = request.args.get("name", "General")
    result = get_body_facts(name)
    result["stats"] = get_body_stats(name, current_app.static_folder)
    return jsonify(result)


@solar_system_bp.route("/community-entries")
def community_entries():
    entity_name = request.args.get("entity_name", "General")

    entries = (
        SolarJournalEntry.query
        .filter_by(entity_name=entity_name, is_public=True)
        .order_by(SolarJournalEntry.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify({
        "success": True,
        "entries": [_entry_to_dict(e, include_author=True) for e in entries]
    })