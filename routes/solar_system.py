from datetime import datetime, timedelta

from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from flask_login import login_user, logout_user, current_user, login_required

from models import db
from models.solar_user import SolarUser, SolarLoginCode
from utils.mailer import send_login_code_email

solar_system_bp = Blueprint(
    "solar_system",
    __name__,
    url_prefix="/solar-system"
)

EARLY_SUPPORTER_LIMIT = 100
RESEND_COOLDOWN_SECONDS = 30


def _is_solar_user() -> bool:
    return current_user.is_authenticated and isinstance(current_user, SolarUser)


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
    return render_template("solar_system/index.html")


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
    return render_template("solar_system/journal.html")


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