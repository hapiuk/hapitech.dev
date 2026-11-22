# utils/security.py — CSRF, login rate limiting, role guards and account scoping.
import datetime as dt
import hmac
import secrets
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for
from flask_login import current_user

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT_PREFIXES = ("/api/v1/",)          # client-site API: authenticated by site key, no cookies

LOGIN_WINDOW = dt.timedelta(minutes=15)
MAX_FAILS_PER_IP = 10
MAX_FAILS_PER_EMAIL = 6


# ---------------------------------------------------------------- CSRF

def csrf_token() -> str:
    tok = session.get("_csrf")
    if not tok:
        tok = session["_csrf"] = secrets.token_urlsafe(32)
    return tok


def _csrf_ok() -> bool:
    expected = session.get("_csrf")
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    return bool(expected and sent and hmac.compare_digest(expected, sent))


def init_security(app):
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _csrf_protect():
        if request.method not in UNSAFE or app.config.get("TESTING_SKIP_CSRF"):
            return None
        if request.path.startswith(CSRF_EXEMPT_PREFIXES):
            return None
        if _csrf_ok():
            return None
        msg = "Your session expired. Refresh the page and try again."
        if request.is_json or request.accept_mimetypes.best == "application/json" or request.path.startswith(
                ("/auth/", "/contact", "/admin/api/", "/portal/api/")):
            return jsonify({"ok": False, "message": msg}), 400
        abort(400, msg)

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith(("/admin", "/portal")):
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp


# ---------------------------------------------------------------- rate limiting (DB-backed)

def client_ip() -> str:
    # NGINX sets X-Forwarded-For; take the first (client) address.
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[0].strip() or request.remote_addr or "?")[:64]


def login_blocked(email: str) -> bool:
    from models import db
    from models.core import LoginAttempt
    since = dt.datetime.utcnow() - LOGIN_WINDOW
    q = db.session.query(LoginAttempt).filter(LoginAttempt.created_at >= since, LoginAttempt.success.is_(False))
    if q.filter(LoginAttempt.ip == client_ip()).count() >= MAX_FAILS_PER_IP:
        return True
    return bool(email) and q.filter(LoginAttempt.email == email).count() >= MAX_FAILS_PER_EMAIL


def record_login(email: str, success: bool, kind: str = "password") -> None:
    from models import db
    from models.core import LoginAttempt
    db.session.add(LoginAttempt(ip=client_ip(), email=(email or "")[:255], success=success, kind=kind))
    # prune old rows now and then
    if secrets.randbelow(50) == 0:
        LoginAttempt.query.filter(LoginAttempt.created_at < dt.datetime.utcnow() - dt.timedelta(days=7)).delete()
    db.session.commit()


# ---------------------------------------------------------------- guards

def _deny():
    if request.path.startswith(("/admin/api/", "/portal/api/")):
        return jsonify({"ok": False, "message": "Please log in again."}), 401
    return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated:
            return _deny()
        if not current_user.is_admin:
            abort(403)
        return fn(*a, **kw)
    return wrapper


def owner_required(fn):
    """Client portal: a logged-in owner/staff user with an account. Admins may view a client's
    portal via ?as=<account slug> (support / demo); everyone else only ever sees their own account."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user.is_authenticated:
            return _deny()
        from models.core import Account
        if current_user.is_admin:
            slug = request.args.get("as") or session.get("portal_as")
            acct = Account.query.filter_by(slug=slug).first() if slug else None
            if not acct:
                return redirect(url_for("admin.clients"))
            session["portal_as"] = acct.slug
        else:
            acct = current_user.account
            if not acct or acct.status == "archived":
                abort(403)
        g.account = acct
        return fn(*a, **kw)
    return wrapper


def scoped(model, **filters):
    """Query helper: every portal query goes through here so it is always limited to g.account."""
    return model.query.filter_by(account_id=g.account.id, **filters)


def safe_next(url: str | None) -> str | None:
    """Only allow same-site relative redirects."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return None
