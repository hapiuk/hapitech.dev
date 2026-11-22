# tests/test_platform.py — end-to-end checks for auth, tenancy, reviews, site API, lab and pages.
# Run: .venv/bin/python -m pytest -q
import io
import json
import os
import re

import pytest
from PIL import Image

os.environ.setdefault("FLASK_DEBUG", "1")


@pytest.fixture()
def app(tmp_path):
    from app import create_app
    from models import db
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "UPLOAD_ROOT": str(tmp_path / "uploads"),
        "MAIL_MODE": "log",
        "PUBLIC_BASE_URL": "https://hapitech.test",
    })
    app.instance_path = str(tmp_path)          # mail outbox + news cache stay in tmp
    with app.app_context():
        db.create_all()
        _seed(db)
    yield app


def _seed(db):
    import datetime as dt
    from models.core import Account, AddOn, User
    from models.reviews import Review
    r = Account(name="Roland's Handyman", slug="rolands", kind="client", domain="rolands.test",
                google_profile_url="https://g.page/r/x/review", contact_name="Roland")
    y = Account(name="Ray G", slug="rayg", kind="client", domain="rayg.test")
    db.session.add_all([r, y])
    db.session.flush()
    for acct in (r, y):
        db.session.add(AddOn(account_id=acct.id, status="trial", trial_ends_at=dt.date.today() + dt.timedelta(days=30)))
    admin = User(email="admin@test", username="admin@test", role="admin", name="Aaron")
    roland = User(email="roland@test", username="roland@test", role="owner", account_id=r.id, name="Roland")
    ray = User(email="ray@test", username="ray@test", role="owner", account_id=y.id, name="Ray")
    db.session.add_all([admin, roland, ray])
    db.session.add(Review(account_id=y.id, author_name="Ray's customer", rating=5, body="Great", source="google"))
    db.session.commit()


def _csrf(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert m, f"no csrf meta on {path}"
    return m.group(1)


def _login(client, email, pw=None, remember=False):
    """Passwordless: ask for a code (returned in the response in local log mode), then verify it."""
    tok = _csrf(client)
    r = client.post("/auth/code/request", json={"email": email}, headers={"X-CSRF-Token": tok})
    code = r.json.get("dev_code", "000000")
    return client.post("/auth/code/verify", json={"code": code, "remember": remember}, headers={"X-CSRF-Token": tok})


def _form(client, path, data, page=None, **kw):
    tok = _csrf(client, page or "/")
    data = {**data, "csrf_token": tok}
    return client.post(path, data=data, **kw)


# ---------------------------------------------------------------- auth

def test_login_routes_by_role(app):
    assert _login(app.test_client(), "admin@test").json["redirect"] == "/admin"
    assert _login(app.test_client(), "roland@test").json["redirect"] == "/portal"


def test_wrong_codes_then_lockout(app):
    c = app.test_client()
    tok = _csrf(c)
    c.post("/auth/code/request", json={"email": "roland@test"}, headers={"X-CSRF-Token": tok})
    for _ in range(5):
        assert c.post("/auth/code/verify", json={"code": "000001"}, headers={"X-CSRF-Token": tok}).status_code == 400
    r = c.post("/auth/code/verify", json={"code": "000001"}, headers={"X-CSRF-Token": tok})
    assert "expired" in r.json["message"]                      # code dead after 5 wrong tries
    r = c.post("/auth/code/request", json={"email": "roland@test"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 429                                 # and the email is rate limited


def test_csrf_required(app):
    assert app.test_client().post("/auth/code/request", json={"email": "admin@test"}).status_code == 400


def test_code_is_emailed(app):
    c = app.test_client()
    tok = _csrf(c)
    assert c.post("/auth/code/request", json={"email": "ray@test"}, headers={"X-CSRF-Token": tok}).json["ok"]
    outbox = os.path.join(app.instance_path, "mail_outbox")
    mail = open(os.path.join(outbox, sorted(os.listdir(outbox))[-1])).read()
    code = re.search(r"login code: (\d{6})", mail).group(1)
    r = c.post("/auth/code/verify", json={"code": code}, headers={"X-CSRF-Token": tok})
    assert r.json["ok"] and r.json["redirect"] == "/portal"


def test_unknown_email_gets_generic_answer(app):
    c = app.test_client()
    tok = _csrf(c)
    r = c.post("/auth/code/request", json={"email": "nobody@test"}, headers={"X-CSRF-Token": tok})
    assert r.json["ok"] and "dev_code" not in r.json
    assert c.post("/auth/code/verify", json={"code": "123456"}, headers={"X-CSRF-Token": tok}).status_code == 400


def test_no_passwords_stored(app):
    from models.core import User
    _login(app.test_client(), "admin@test")
    with app.app_context():
        assert all(u.password_hash == "" for u in User.query.all())


def test_logout_really_logs_out_even_with_remember_me(app):
    c = app.test_client()
    assert _login(c, "roland@test", remember=True).json["ok"]
    assert c.get("/portal/").status_code == 200
    tok = _csrf(c, "/portal/")
    assert c.post("/logout", data={"csrf_token": tok}).status_code == 302
    assert c.get("/portal/").status_code == 302                 # bounced to login


# ---------------------------------------------------------------- access control

def test_owner_cannot_reach_admin(app):
    c = app.test_client()
    _login(c, "roland@test")
    assert c.get("/admin/").status_code == 403
    assert c.get("/admin/clients").status_code == 403


def test_anonymous_redirected_to_login(app):
    c = app.test_client()
    r = c.get("/portal/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_tenancy_owner_cannot_touch_other_account(app):
    from models import db
    from models.reviews import Review
    c = app.test_client()
    _login(c, "roland@test")
    with app.app_context():
        rays = Review.query.filter_by(author_name="Ray's customer").first().id
    # Roland's portal never lists Ray's review...
    assert "Ray's customer" not in c.get("/portal/reviews").get_data(as_text=True)
    # ...and can't act on it by id
    r = _form(c, f"/portal/reviews/{rays}", {"action": "reply", "body": "hijack"}, page="/portal/reviews")
    assert r.status_code == 404
    with app.app_context():
        assert not db.session.get(Review, rays).replies


# ---------------------------------------------------------------- review flow

def _png():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 50, 50)).save(buf, "PNG")
    buf.seek(0)
    return buf


def test_review_request_to_published_review(app):
    from models.reviews import Review, ReviewRequest
    c = app.test_client()
    _login(c, "roland@test")
    r = _form(c, "/portal/ask", {"customer_name": "Sarah", "job_ref": "Wardrobe"}, page="/portal/ask")
    assert r.status_code == 302
    send_url = r.headers["Location"]
    send = c.get(send_url).get_data(as_text=True)
    assert "Ask Sarah to scan this" in send and "sms:" not in send
    _form(c, send_url, {"email": "sarah@example.com"}, page=send_url)      # emailed, address not kept
    with app.app_context():
        rq = ReviewRequest.query.filter_by(customer_name="Sarah").first()
        assert rq.sent_via == "email" and rq.contact is None
    with app.app_context():
        token = ReviewRequest.query.filter_by(customer_name="Sarah").first().token
    assert f"https://hapitech.test/r/{token}" in send

    cust = app.test_client()
    page = cust.get(f"/r/{token}")
    assert page.status_code == 200 and "How did Roland do" in page.get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True)).group(1)
    r = cust.post(f"/r/{token}", data={"csrf_token": tok, "rating": "5", "name": "Sarah", "body": "Brilliant",
                                        "photos": (_png(), "pic.png")}, content_type="multipart/form-data")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "Post it on Google" in body
    with app.app_context():
        rev = Review.query.filter_by(author_name="Sarah").first()
        assert rev.verified and rev.rating == 5 and len(json.loads(rev.photos)) == 1
    # single use
    again = cust.get(f"/r/{token}").get_data(as_text=True)
    assert "already left a review" in again


def test_uploaded_photo_has_no_exif(app, tmp_path):
    from PIL import Image as I
    with app.test_request_context():
        from models.core import Account
        from utils.uploads import save_image
        from werkzeug.datastructures import FileStorage
        buf = io.BytesIO()
        img = I.new("RGB", (50, 50))
        exif = img.getexif()
        exif[0x8825] = {2: (51, 30, 0)}          # GPS IFD
        img.save(buf, "JPEG", exif=exif)
        buf.seek(0)
        acct = Account.query.filter_by(slug="rolands").first()
        path, w, h = save_image(FileStorage(buf, filename="x.jpg"), acct)
        out = I.open(os.path.join(app.config["UPLOAD_ROOT"], path))
        assert not out.getexif()


def test_owner_report_keeps_review_visible(app):
    from models.reviews import Review
    c = app.test_client()
    _login(c, "ray@test")
    with app.app_context():
        rid = Review.query.filter_by(author_name="Ray's customer").first().id
    _form(c, f"/portal/reviews/{rid}", {"action": "report", "reason": "Not my customer"}, page="/portal/reviews")
    with app.app_context():
        assert Review.query.get(rid).status == "reported"
    # still shown publicly until an admin decides
    assert "Ray&#39;s customer" in app.test_client().get("/reviews/rayg").get_data(as_text=True)


# ---------------------------------------------------------------- site API

def test_site_api_requires_key_and_returns_reviews(app):
    from models import db
    from models.core import Account
    from werkzeug.security import generate_password_hash
    c = app.test_client()
    assert c.get("/api/v1/sites/rayg/reviews").status_code == 401
    with app.app_context():
        a = Account.query.filter_by(slug="rayg").first()
        a.site_api_key_hash = generate_password_hash("ht_test")
        db.session.commit()
    assert c.get("/api/v1/sites/rayg/reviews", headers={"X-Site-Key": "wrong"}).status_code == 401
    r = c.get("/api/v1/sites/rayg/reviews", headers={"X-Site-Key": "ht_test"})
    assert r.status_code == 200 and r.json["count"] == 1 and r.json["reviews"][0]["source"] == "google"
    # a key for one site doesn't open another
    assert c.get("/api/v1/sites/rolands/reviews", headers={"X-Site-Key": "ht_test"}).status_code == 401


# ---------------------------------------------------------------- lab

SAMPLE = [
    {"ts": "2026-11-03T09:52:19Z", "test_id": "t-1", "model": "unsloth/Demo-7B-GGUF", "repeat": 1, "passed": True,
     "prefill": {"tokens_per_second": 400, "prompt_tokens": 10}, "decode": {"tokens_per_second": 120, "completion_tokens": 5},
     "ttft_ms": 90, "total_seconds": 0.5},
    {"ts": "2026-11-03T09:52:20Z", "test_id": "t-1", "model": "unsloth/Demo-7B-GGUF", "repeat": 2, "passed": False,
     "decode": {"tokens_per_second": 100}, "ttft_ms": 110},
    {"ts": "2026-11-04T00:00:00", "test_id": "t-1", "model": "Demo-7B-UD-IQ3_XXS", "repeat": None, "passed": True},
]


def test_bench_upload_publish_flow(app):
    from models import db
    from models.bench import BenchModel, BenchPrompt, BenchRun
    with app.app_context():
        db.session.add(BenchModel(slug="unsloth/Demo-7B-GGUF", display_name="Demo 7B", status="active"))
        db.session.add(BenchPrompt(slug="t-1", name="Test one", prompt_text="Say hi"))
        db.session.commit()
    c = app.test_client()
    _login(c, "admin@test")
    text = "\n".join(json.dumps(x) for x in SAMPLE)
    r = _form(c, "/admin/lab/runs/new", {"jsonl": text}, page="/admin/lab/runs/new")
    assert r.status_code == 302
    with app.app_context():
        runs = BenchRun.query.order_by(BenchRun.id).all()
        assert len(runs) == 2                                   # repeats grouped; quant-suffixed name matched
        assert [len(x.results) for x in runs] == [2, 1]
        assert runs[0].pass_rate == 0.5 and runs[0].avg("decode_tps") == 110
        rid = runs[0].id
    assert app.test_client().get(f"/lab/runs/{rid}").status_code == 404     # drafts are private
    _form(c, f"/admin/lab/runs/{rid}", {"action": "publish"}, page=f"/admin/lab/runs/{rid}")
    assert app.test_client().get(f"/lab/runs/{rid}").status_code == 200
    assert "HapiTech Lab" in app.test_client().get("/news").get_data(as_text=True)


def test_bad_jsonl_is_rejected(app):
    c = app.test_client()
    _login(c, "admin@test")
    r = _form(c, "/admin/lab/runs/new", {"jsonl": "{not json"}, page="/admin/lab/runs/new")
    assert r.status_code == 200 and "Line 1" in r.get_data(as_text=True)


# ---------------------------------------------------------------- pages render

ADMIN_PAGES = ["/admin/", "/admin/clients", "/admin/clients/new", "/admin/clients/rolands",
               "/admin/clients/rolands?tab=jobs", "/admin/clients/rolands?tab=money", "/admin/clients/rolands?tab=users",
               "/admin/clients/rolands?tab=reviews", "/admin/clients/rolands?tab=site", "/admin/reviews",
               "/admin/reviews/new", "/admin/requests", "/admin/settings", "/admin/lab/runs", "/admin/lab/runs/new",
               "/admin/lab/prompts", "/admin/lab/prompts/new", "/admin/lab/models", "/admin/lab/models/new"]
PORTAL_PAGES = ["/portal/", "/portal/ask", "/portal/requests", "/portal/reviews", "/portal/posts", "/portal/posts/new",
                "/portal/website", "/portal/help"]
PUBLIC_PAGES = ["/", "/news", "/privacy", "/terms", "/login", "/lab", "/reviews/rolands", "/reviews/rolands/write"]


def test_all_pages_render(app):
    a = app.test_client()
    _login(a, "admin@test")
    for p in ADMIN_PAGES:
        assert a.get(p).status_code == 200, p
    o = app.test_client()
    _login(o, "roland@test")
    for p in PORTAL_PAGES:
        assert o.get(p).status_code == 200, p
    anon = app.test_client()
    for p in PUBLIC_PAGES:
        assert anon.get(p).status_code == 200, p


def test_admin_can_view_client_portal(app):
    c = app.test_client()
    _login(c, "admin@test")
    r = c.get("/admin/clients/rolands/portal", follow_redirects=True)
    assert r.status_code == 200 and "Back to admin" in r.get_data(as_text=True)


def test_addon_paused_shows_upsell(app):
    from models import db
    from models.core import AddOn, Account
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        AddOn.query.filter_by(account_id=a.id).first().status = "paused"
        db.session.commit()
    c = app.test_client()
    _login(c, "roland@test")
    assert "Get more reviews, the easy way" in c.get("/portal/ask").get_data(as_text=True)


def test_open_review_form_from_site_button(app, monkeypatch):
    import routes.reviews_public as rp
    from models.reviews import Review
    c = app.test_client()
    html = c.get("/reviews/rolands/write").get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
    t = re.search(r'name="t" value="([^"]+)"', html).group(1)
    base = {"csrf_token": tok, "t": t, "rating": "4", "name": "Jo", "body": "Good job"}
    c.post("/reviews/rolands/write", data=base)                       # instant submit: dropped as a bot
    monkeypatch.setattr(rp, "MIN_SECONDS_TO_WRITE", 0)
    c.post("/reviews/rolands/write", data={**base, "website": "spam"})  # honeypot: dropped
    with app.app_context():
        assert not Review.query.filter_by(author_name="Jo").first()
    assert c.post("/reviews/rolands/write", data=base).status_code == 200
    with app.app_context():
        rv = Review.query.filter_by(author_name="Jo").first()
        assert rv and rv.source == "website" and not rv.verified and rv.rating == 4
    for _ in range(3):
        r = c.post("/reviews/rolands/write", data={**base, "name": "Again"})
    assert "already left reviews today" in r.get_data(as_text=True)


def test_write_form_forwards_to_google_without_addon(app):
    from models import db
    from models.core import AddOn, Account
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        AddOn.query.filter_by(account_id=a.id).first().status = "paused"
        db.session.commit()
    r = app.test_client().get("/reviews/rolands/write")
    assert r.status_code == 302 and r.headers["Location"] == "https://g.page/r/x/review"
