# routes/auth.py — passwordless login: enter your email, get a 6-digit code, done.
# No passwords are stored anywhere. Codes are single-use, expire after 10 minutes,
# are kept only as an HMAC in the signed session cookie, and are rate limited.
import datetime as dt
import hashlib
import hmac
import secrets

from flask import Blueprint, current_app, jsonify, make_response, redirect, render_template, request, session
from flask_login import current_user, login_user, logout_user

from models import db
from models.core import User
from utils.mailer import send_email
from utils.security import login_blocked, record_login, safe_next

auth_bp = Blueprint("auth", __name__)

BLOCKED = "Too many attempts. Please wait 15 minutes and try again."
CODE_TTL = dt.timedelta(minutes=10)
MAX_TRIES = 5


def _find_user(email: str):
    email = (email or "").strip().lower()
    if not email:
        return None
    return User.query.filter(db.func.lower(User.email) == email).first()


def _code_hash(code: str) -> str:
    return hmac.new(current_app.config["SECRET_KEY"].encode(), code.encode(), hashlib.sha256).hexdigest()


@auth_bp.route("/login")
def login():
    """Full-page login: no-JS fallback and the target of protected-page redirects."""
    if current_user.is_authenticated:
        return redirect(safe_next(request.args.get("next")) or current_user.home_url)
    return render_template("auth/login.html", next=safe_next(request.args.get("next")))


@auth_bp.route("/auth/code/request", methods=["POST"])
def code_request():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    generic = {"ok": True, "message": "If that email has an account, a 6-digit code is on its way."}
    if "@" not in email:
        return jsonify({"ok": False, "message": "Enter your email address."}), 400
    if login_blocked(email):
        return jsonify({"ok": False, "message": BLOCKED}), 429
    user = _find_user(email)
    if not (user and user.is_active):
        record_login(email, False, "code")        # counts towards the limit; same answer either way
        session["otp"] = {"uid": None, "e": email, "h": "", "exp": (dt.datetime.utcnow() + CODE_TTL).isoformat(),
                          "tries": 0}
        return jsonify(generic)
    code = f"{secrets.randbelow(1_000_000):06d}"
    session["otp"] = {"uid": user.id, "e": email, "h": _code_hash(code),
                      "exp": (dt.datetime.utcnow() + CODE_TTL).isoformat(), "tries": 0}
    try:
        from utils import email_html
        email_html.send(user.email, f"Your HapiTech login code: {code}", heading="Your login code",
                        lines=["Type this code into the login box. It works for 10 minutes."], code=code,
                        after=["Didn't ask for it? You can ignore this email. Nobody can log in without the code."])
    except Exception as exc:
        print(f"[OTP_EMAIL_ERROR] {exc}")
        return jsonify({"ok": False, "message": "We couldn't send the email just now. Please try again shortly."}), 500
    if current_app.config.get("MAIL_MODE") == "log":     # local development only: nothing is really emailed
        return jsonify({**generic, "message": f"Local test mode: your code is {code}", "dev_code": code})
    return jsonify(generic)


@auth_bp.route("/auth/code/verify", methods=["POST"])
def code_verify():
    data = request.get_json(silent=True) or {}
    code = "".join(ch for ch in (data.get("code") or "") if ch.isdigit())
    otp = session.get("otp")
    if not otp:
        return jsonify({"ok": False, "message": "Ask for a new code first."}), 400
    if dt.datetime.utcnow() > dt.datetime.fromisoformat(otp["exp"]) or otp["tries"] >= MAX_TRIES:
        session.pop("otp", None)
        return jsonify({"ok": False, "message": "That code has expired. Ask for a new one."}), 400
    if not otp["uid"] or not hmac.compare_digest(otp["h"], _code_hash(code)):
        otp["tries"] += 1
        session["otp"] = otp
        record_login(otp.get("e", ""), False, "code")          # counts against this email's limit
        return jsonify({"ok": False, "message": "That code isn't right. Check the email and try again."}), 400
    session.pop("otp", None)
    user = db.session.get(User, otp["uid"])
    if not (user and user.is_active):
        return jsonify({"ok": False, "message": "Account not available."}), 400
    record_login(user.email, True, "code")
    login_user(user, remember=bool(data.get("remember")))
    user.last_login_at = dt.datetime.utcnow()
    db.session.commit()
    session.pop("portal_as", None)
    return jsonify({"ok": True, "redirect": safe_next(request.args.get("next")) or user.home_url})


def send_invite(user: User, inviter: str = "Aaron at HapiTech"):
    """Tell a new client user their dashboard exists. No password to set: they log in with a code."""
    from utils.links import public_url
    biz = user.account.name if user.account else "HapiTech"
    from utils import email_html
    email_html.send(user.email, f"Your {biz} dashboard is ready",
                    heading=f"Hi {(user.name or '').split()[0] if user.name else 'there'}, your dashboard is ready",
                    lines=[f"{inviter} has set up your dashboard for {biz}.",
                           "To log in, tap the button and enter this email address. We'll email you a 6-digit code. "
                           "There's no password to remember."],
                    box=[("Your login email", user.email)],
                    button={"label": "Log in to your dashboard", "url": public_url("/login")},
                    after=["Tip: once you're in, add it to your phone's home screen so it opens like an app."])


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # Clear the session FIRST, then let Flask-Login mark the "keep me logged in" cookie for removal.
    # (Doing it the other way round wipes that marker and the cookie logs you straight back in.)
    session.clear()
    logout_user()
    resp = make_response(jsonify({"ok": True, "redirect": "/"}) if request.is_json else redirect("/"))
    resp.delete_cookie(current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token"))
    return resp
