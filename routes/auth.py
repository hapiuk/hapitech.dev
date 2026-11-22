# routes/auth.py — login (modal + full page), email codes, invites/resets, logout.
import datetime as dt
import hashlib
import hmac
import secrets

from flask import (Blueprint, current_app, jsonify, redirect, render_template, request, session,
                   url_for)
from flask_login import current_user, login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models import db
from models.core import User
from utils.mailer import send_email
from utils.security import login_blocked, record_login, safe_next

auth_bp = Blueprint("auth", __name__)

GENERIC_FAIL = "That email and password don't match. Please try again."
BLOCKED = "Too many attempts. Please wait 15 minutes and try again."
CODE_TTL = dt.timedelta(minutes=10)
TOKEN_MAX_AGE = 60 * 60 * 48          # invite / reset links: 48 hours


def _find_user(email: str):
    email = (email or "").strip().lower()
    if not email:
        return None
    return User.query.filter(db.func.lower(User.email) == email).first()


def _finish_login(user: User, remember: bool):
    login_user(user, remember=remember)
    user.last_login_at = dt.datetime.utcnow()
    db.session.commit()
    session.pop("portal_as", None)
    return jsonify({"ok": True, "redirect": safe_next(request.args.get("next")) or user.home_url})


@auth_bp.route("/login")
def login():
    """Full-page login: no-JS fallback and the target of login_required redirects."""
    if current_user.is_authenticated:
        return redirect(safe_next(request.args.get("next")) or current_user.home_url)
    return render_template("auth/login.html", next=safe_next(request.args.get("next")))


@auth_bp.route("/auth/login", methods=["POST"])
def login_password():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if login_blocked(email):
        return jsonify({"ok": False, "message": BLOCKED}), 429
    user = _find_user(email)
    if not (user and user.is_active and user.check_password(password)):
        record_login(email, False)
        return jsonify({"ok": False, "message": GENERIC_FAIL}), 401
    record_login(email, True)
    return _finish_login(user, remember=bool(data.get("remember")))


# ---------------------------------------------------------------- email code

def _code_hash(code: str) -> str:
    return hmac.new(current_app.config["SECRET_KEY"].encode(), code.encode(), hashlib.sha256).hexdigest()


@auth_bp.route("/auth/code/request", methods=["POST"])
def code_request():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    generic = {"ok": True, "message": "If that email has an account, a 6-digit code is on its way."}
    if not email:
        return jsonify({"ok": False, "message": "Enter your email address."}), 400
    if login_blocked(email):
        return jsonify({"ok": False, "message": BLOCKED}), 429
    user = _find_user(email)
    if not (user and user.is_active):
        record_login(email, False, "code")        # counts towards the limit; no enumeration
        return jsonify(generic)
    code = f"{secrets.randbelow(1_000_000):06d}"
    session["otp"] = {"uid": user.id, "h": _code_hash(code), "exp": (dt.datetime.utcnow() + CODE_TTL).isoformat(),
                      "tries": 0}
    try:
        send_email(to=user.email, subject=f"Your HapiTech login code: {code}",
                   text=f"Your HapiTech login code is {code}\n\nIt expires in 10 minutes. "
                        f"If you didn't ask for it, you can ignore this email.")
    except Exception as exc:
        print(f"[OTP_EMAIL_ERROR] {exc}")
        return jsonify({"ok": False, "message": "We couldn't send the email just now. Try your password instead."}), 500
    return jsonify(generic)


@auth_bp.route("/auth/code/verify", methods=["POST"])
def code_verify():
    data = request.get_json(silent=True) or {}
    code = "".join(ch for ch in (data.get("code") or "") if ch.isdigit())
    otp = session.get("otp")
    if not otp:
        return jsonify({"ok": False, "message": "Ask for a new code first."}), 400
    if dt.datetime.utcnow() > dt.datetime.fromisoformat(otp["exp"]) or otp["tries"] >= 5:
        session.pop("otp", None)
        return jsonify({"ok": False, "message": "That code has expired. Ask for a new one."}), 400
    if not hmac.compare_digest(otp["h"], _code_hash(code)):
        otp["tries"] += 1
        session["otp"] = otp
        return jsonify({"ok": False, "message": "That code isn't right. Check the email and try again."}), 400
    session.pop("otp", None)
    user = db.session.get(User, otp["uid"])
    if not (user and user.is_active):
        return jsonify({"ok": False, "message": "Account not available."}), 400
    record_login(user.email, True, "code")
    return _finish_login(user, remember=bool(data.get("remember")))


# ---------------------------------------------------------------- invites & resets

def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="set-password")


def make_password_token(user: User) -> str:
    # include a fragment of the current hash so the link dies once the password changes
    return _serializer().dumps({"uid": user.id, "p": user.password_hash[-12:]})


def password_link(user: User) -> str:
    from utils.links import public_url
    return public_url(url_for("auth.set_password", token=make_password_token(user)))


def send_invite(user: User, inviter: str = "Aaron at HapiTech"):
    link = password_link(user)
    biz = user.account.name if user.account else "HapiTech"
    send_email(
        to=user.email, subject=f"Your {biz} dashboard is ready",
        text=(f"Hi {user.name or ''},\n\n{inviter} has set up your dashboard for {biz}.\n\n"
              f"Choose your password here (the link works for 48 hours):\n{link}\n\n"
              f"After that, log in any time from the \"Client login\" button on hapitech.dev.\n"),
    )


@auth_bp.route("/auth/forgot", methods=["POST"])
def forgot():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if login_blocked(email):
        return jsonify({"ok": False, "message": BLOCKED}), 429
    user = _find_user(email)
    if user and user.is_active:
        try:
            send_email(to=user.email, subject="Reset your HapiTech password",
                       text=f"Use this link to choose a new password (valid for 48 hours):\n{password_link(user)}\n\n"
                            f"If you didn't ask for this, you can ignore it.")
        except Exception as exc:
            print(f"[RESET_EMAIL_ERROR] {exc}")
    else:
        record_login(email, False, "reset")
    return jsonify({"ok": True, "message": "If that email has an account, a reset link is on its way."})


@auth_bp.route("/auth/set-password/<token>", methods=["GET", "POST"])
def set_password(token):
    try:
        data = _serializer().loads(token, max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        return render_template("auth/set_password.html", error="This link has expired. Ask for a new one."), 400
    except BadSignature:
        return render_template("auth/set_password.html", error="This link isn't valid."), 400
    user = db.session.get(User, data.get("uid"))
    if not user or user.password_hash[-12:] != data.get("p"):
        return render_template("auth/set_password.html", error="This link has already been used."), 400
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        if len(pw) < 10:
            return render_template("auth/set_password.html", user=user, error="Use at least 10 characters.")
        if pw != pw2:
            return render_template("auth/set_password.html", user=user, error="The two passwords don't match.")
        user.set_password(pw)
        db.session.commit()
        login_user(user)
        return redirect(user.home_url)
    return render_template("auth/set_password.html", user=user)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    if request.is_json:
        return jsonify({"ok": True, "redirect": "/"})
    return redirect("/")
