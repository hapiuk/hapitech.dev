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
               "/admin/clients/rolands?tab=reviews", "/admin/clients/rolands?tab=site", "/admin/clients/rolands?tab=traffic", "/admin/reviews",
               "/admin/reviews/new", "/admin/requests", "/admin/settings", "/admin/lab/runs", "/admin/lab/runs/new",
               "/admin/lab/prompts", "/admin/lab/prompts/new", "/admin/lab/models", "/admin/lab/models/new", "/admin/work"]
PORTAL_PAGES = ["/portal/", "/portal/visitors", "/portal/website/hero", "/portal/ask", "/portal/requests", "/portal/reviews", "/portal/posts", "/portal/posts/new", "/portal/jobs", "/portal/jobs/new", "/portal/calendar", "/portal/settings",
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


def test_app_manifest_is_client_branded(app):
    c = app.test_client()
    m = c.get("/app/rolands/manifest.webmanifest")
    assert m.status_code == 200 and m.headers["Content-Type"].startswith("application/manifest+json")
    data = json.loads(m.get_data(as_text=True))
    assert data["name"] == "Roland's Handyman" and data["start_url"] == "/portal/" and "HapiTech" not in data["name"]
    assert c.get("/app/_hapitech/manifest.webmanifest").json["name"] == "HapiTech Admin"
    icon = c.get("/app/rolands/icon-192.png")
    assert icon.status_code == 200 and icon.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert c.get("/app/rolands/icon-999.png").status_code == 404
    assert c.get("/app/nope/manifest.webmanifest").status_code == 404
    assert "serviceWorker" not in c.get("/portal/sw.js").get_data(as_text=True)  # it's the worker itself
    _login(c, "roland@test")
    page = c.get("/portal/").get_data(as_text=True)
    assert '/app/rolands/manifest.webmanifest' in page and 'id="installBanner"' in page


def test_site_blocks_match_definitions(app):
    from models.core import Account
    from models.content import ContentBlock
    from utils.content_blocks import ensure_blocks
    from models import db
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.domain = "rolandshandyman.co.uk"
        assert ensure_blocks(a, None) == 8
        db.session.commit()
        assert ensure_blocks(a, None) == 0                     # idempotent
        assert ContentBlock.query.filter_by(account_id=a.id, key="services.wall.title").first().data == "Wall Mounting Service"


# ---------------------------------------------------------------- jobs: enquiry -> quote -> booking -> done -> invoice

def _outbox(app):
    d = os.path.join(app.instance_path, "mail_outbox")
    return [open(os.path.join(d, f)).read() for f in sorted(os.listdir(d))] if os.path.isdir(d) else []


def _site_key(app, slug):
    from models import db
    from models.core import Account
    from werkzeug.security import generate_password_hash
    with app.app_context():
        a = Account.query.filter_by(slug=slug).first()
        a.site_api_key_hash = generate_password_hash("ht_k")
        a.contact_email = "roland-owner@test"
        db.session.commit()
    return {"X-Site-Key": "ht_k"}


def test_job_lifecycle(app):
    import datetime as dt
    from models import db
    from models.work import Invoice, Lead, Quote
    from utils.tasks import run_all
    c = app.test_client()
    hdr = _site_key(app, "rolands")
    r = c.post("/api/v1/sites/rolands/enquiries", json={"name": "Sam Smith", "email": "sam@example.com",
                                                        "postcode": "wv1 1aa", "job": "Fit a wardrobe"}, headers=hdr)
    assert r.status_code == 201
    lid = r.json["id"]
    o = app.test_client()
    _login(o, "roland@test")
    assert "Sam Smith" in o.get("/portal/jobs").get_data(as_text=True)
    # quote
    page = f"/portal/jobs/{lid}/quote"
    r = _form(o, page, {"desc": ["Labour", "Fixings"], "qty": ["1", "2"], "price": ["120", "5"], "vat_rate": "0",
                        "action": "send"}, page=page)
    assert r.status_code == 302
    with app.app_context():
        q = Quote.query.filter_by(lead_id=lid).first()
        assert q.status == "sent" and q.totals[2] == 130.0 and Lead.query.get(lid).status == "quoted"
        token = q.token
    assert any("/q/" + token in m for m in _outbox(app))
    # customer accepts
    cust = app.test_client()
    html = cust.get(f"/q/{token}").get_data(as_text=True)
    assert "£130.00" in html and "Accept this quote" in html
    tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    cust.post(f"/q/{token}", data={"csrf_token": tok, "answer": "accept"})
    with app.app_context():
        assert Lead.query.get(lid).status == "accepted"
    # book for tomorrow 10:00, with confirmation
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    _form(o, f"/portal/jobs/{lid}", {"action": "book", "date": tomorrow, "time": "10:00", "days": "1", "notify": "1"},
          page=f"/portal/jobs/{lid}")
    assert any("You're booked in" in m for m in _outbox(app))
    # day-before reminder via the scheduler (force, and pretend it's after 8am)
    with app.app_context():
        lead = Lead.query.get(lid)
        assert lead.status == "booked" and lead.confirm_sent_at
    import utils.tasks as tasks
    real = tasks.dt.datetime
    class FakeDT(real):
        @classmethod
        def utcnow(cls):
            return real.combine(real.utcnow().date(), real.min.time()).replace(hour=9)
    tasks.dt.datetime = FakeDT
    try:
        assert run_all(app, force=True)["reminders"] == 1
        assert run_all(app, force=True)["reminders"] == 0          # only once
    finally:
        tasks.dt.datetime = real
    # done -> review email; then invoice prefilled from the quote, sent, paid
    _form(o, f"/portal/jobs/{lid}", {"action": "done", "ask_review": "1"}, page=f"/portal/jobs/{lid}")
    assert any("Leave a review" in m for m in _outbox(app))
    ipage = f"/portal/jobs/{lid}/invoice"
    assert "Labour" in o.get(ipage).get_data(as_text=True)          # copied from the accepted quote
    _form(o, ipage, {"desc": ["Labour", "Fixings"], "qty": ["1", "2"], "price": ["120", "5"], "vat_rate": "0",
                     "action": "send"}, page=ipage)
    with app.app_context():
        inv = Invoice.query.filter_by(lead_id=lid).first()
        assert inv.status == "sent" and inv.number == "INV-0001"
        itok, iid = inv.token, inv.id
    assert "INV-0001" in cust.get(f"/i/{itok}").get_data(as_text=True)
    _form(o, f"/portal/jobs/{lid}/invoice/{iid}", {"action": "paid", "desc": ["x"], "qty": ["1"], "price": ["1"]},
          page=f"/portal/jobs/{lid}/invoice/{iid}")
    with app.app_context():
        assert Invoice.query.get(iid).status == "paid"
    # accepted/done jobs can't be deleted until archived
    _form(o, f"/portal/jobs/{lid}", {"action": "delete"}, page=f"/portal/jobs/{lid}")
    with app.app_context():
        assert Lead.query.get(lid) is not None
    _form(o, f"/portal/jobs/{lid}", {"action": "archive"}, page=f"/portal/jobs/{lid}")
    _form(o, f"/portal/jobs/{lid}", {"action": "delete"}, page=f"/portal/jobs/{lid}")
    with app.app_context():
        assert Lead.query.get(lid) is None and Quote.query.count() == 0      # details gone with it


def test_declined_jobs_auto_deleted_after_30_days(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    from utils.tasks import run_all
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        old = Lead(account_id=a.id, name="Old", status="declined", declined_at=dt.datetime.utcnow() - dt.timedelta(days=31))
        recent = Lead(account_id=a.id, name="Recent", status="declined", declined_at=dt.datetime.utcnow() - dt.timedelta(days=2))
        done = Lead(account_id=a.id, name="Done", status="done", done_at=dt.datetime.utcnow() - dt.timedelta(days=400))
        db.session.add_all([old, recent, done])
        db.session.commit()
    assert run_all(app, force=True)["deleted"] == 1
    with app.app_context():
        assert {l.name for l in Lead.query.all()} == {"Recent", "Done"}


def test_new_enquiry_can_be_deleted_straight_away(app):
    from models import db
    from models.core import Account
    from models.work import Lead
    with app.app_context():
        lid = Lead(account_id=Account.query.filter_by(slug="rolands").first().id, name="Nope")
        db.session.add(lid); db.session.commit(); lid = lid.id
    o = app.test_client()
    _login(o, "roland@test")
    _form(o, f"/portal/jobs/{lid}", {"action": "delete"}, page=f"/portal/jobs/{lid}")
    with app.app_context():
        assert Lead.query.get(lid) is None


def test_calendar_feed(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    o = app.test_client()
    _login(o, "roland@test")
    assert o.get("/portal/calendar").status_code == 200
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        db.session.add(Lead(account_id=a.id, name="Pat", title="Shelves", status="booked", postcode="WV2 2AA",
                            start_at=dt.datetime.utcnow() + dt.timedelta(days=3)))
        db.session.commit()
        token = a.calendar_token
    ics = app.test_client().get(f"/cal/{token}.ics")
    body = ics.get_data(as_text=True)
    assert ics.status_code == 200 and "BEGIN:VCALENDAR" in body and "Shelves – Pat" in body and "WV2 2AA" in body
    assert app.test_client().get("/cal/wrong-token-wrong-token-wrong.ics").status_code == 404


def test_helper_restrictions(app):
    from models import db
    from models.core import Account, User
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        db.session.add(User(email="helper@test", username="helper@test", role="staff", account_id=a.id))
        db.session.commit()
    h = app.test_client()
    _login(h, "helper@test")
    assert h.get("/portal/jobs").status_code == 200
    assert h.get("/portal/settings").status_code == 302                  # bounced
    assert h.get("/portal/website").status_code == 302
    assert "Settings" not in h.get("/portal/").get_data(as_text=True).split('class="side__nav"')[1].split("</nav>")[0]


def test_away_mode_in_content_api(app):
    import datetime as dt
    hdr = _site_key(app, "rolands")
    o = app.test_client()
    _login(o, "roland@test")
    back = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    _form(o, "/portal/settings", {"action": "away", "away_until": back, "away_message": "On holiday"}, page="/portal/settings")
    away = app.test_client().get("/api/v1/sites/rolands/content", headers=hdr).json["away"]
    assert away == {"until": back, "message": "On holiday"}


def test_admin_sees_all_jobs(app):
    from models import db
    from models.core import Account
    from models.work import Lead
    with app.app_context():
        for slug in ("rolands", "rayg"):
            db.session.add(Lead(account_id=Account.query.filter_by(slug=slug).first().id, name=f"Cust {slug}"))
        db.session.commit()
    a = app.test_client()
    _login(a, "admin@test")
    html = a.get("/admin/work").get_data(as_text=True)
    assert "Cust rolands" in html and "Cust rayg" in html


def test_setup_clients_creates_switched_off_owner_logins(app):
    from models.core import User
    runner = app.test_cli_runner()
    with app.app_context():
        res = runner.invoke(args=["setup-clients"])
        assert res.exit_code == 0, res.output
    with app.app_context():
        u = User.query.filter_by(email="enquiries@rolandshandyman.co.uk").first()
        assert u and u.role == "owner" and not u.is_active and u.account.contact_email == u.email
    r = _login(app.test_client(), "enquiries@rolandshandyman.co.uk")
    assert r.status_code == 400                                   # can't log in until invited


def test_photo_likes_and_hero_choice(app):
    hdr = _site_key(app, "rolands")
    c = app.test_client()
    photos = ["img/gallery/a.jpg", "img/gallery/b.jpg", "img/gallery/c.jpg"]
    assert c.post("/api/v1/sites/rolands/defaults", json={"photos": {"gallery": photos}}, headers=hdr).json["ok"]
    like = lambda p, d=1: c.post("/api/v1/sites/rolands/likes", json={"photo": p, "delta": d}, headers=hdr)
    assert like("img/gallery/not-ours.jpg").status_code == 404           # only the site's own photos
    assert like("img/gallery/b.jpg").json["count"] == 1
    assert like("img/gallery/b.jpg").json["count"] == 2
    assert like("img/gallery/c.jpg").json["count"] == 1
    assert like("img/gallery/a.jpg", -1).json["count"] == 0              # never below zero
    content = lambda: c.get("/api/v1/sites/rolands/content", headers=hdr).json
    assert content()["likes"] == {"img/gallery/b.jpg": 2, "img/gallery/c.jpg": 1}
    assert content()["hero"] is None                                     # default: site's own random choice
    assert "hero.mode" not in content()["content"]
    o = app.test_client()
    _login(o, "roland@test")
    assert "Top-of-page photo" in o.get("/portal/website/hero").get_data(as_text=True)
    _form(o, "/portal/website/hero", {"mode": "liked"}, page="/portal/website/hero")
    assert content()["hero"] == ["img/gallery/b.jpg", "img/gallery/c.jpg"]  # most liked first
    _form(o, "/portal/website/hero", {"mode": "chosen", "pick": ["img/gallery/a.jpg", "img/gallery/zzz.jpg"]},
          page="/portal/website/hero")
    assert content()["hero"] == ["img/gallery/a.jpg"]                    # unknown photos ignored
    _form(o, "/portal/website/hero", {"mode": "all"}, page="/portal/website/hero")
    assert content()["hero"] is None



def test_emails_are_styled_with_plain_text_fallback(app):
    import email
    c = app.test_client()
    tok = _csrf(c)
    c.post("/auth/code/request", json={"email": "ray@test"}, headers={"X-CSRF-Token": tok})
    raw = _outbox(app)[-1]
    msg = email.message_from_string(raw)
    types = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in types and "text/html" in types
    html = next(p for p in msg.walk() if p.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert "Your login code" in html and "max-width:560px" in html


def test_repeat_reminder_sent_from_background(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead, RepeatReminder
    from utils.tasks import run_all
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        lead = Lead(account_id=a.id, name="Kim Lee", email="kim@example.com", status="done", title="Gutters")
        db.session.add(lead); db.session.flush()
        db.session.add(RepeatReminder(account_id=a.id, lead_id=lead.id, remind_on=dt.date.today(), note="clearing the gutters"))
        db.session.commit()
    assert run_all(app, force=True)["repeat"] == 1                 # builds its "stop" link without a web request
    assert any("clearing the gutters" in m and "/u/" in m for m in _outbox(app))


def test_client_update_notes(app):
    from models.core import Account
    from utils import updates
    with app.test_request_context("/"):
        secs = updates.sections("docs/drafts/whats-new-after-invite.md")
        assert secs and secs[0]["title"]
        roland = Account.query.filter_by(slug="rolands").first()
        ray = Account.query.filter_by(slug="rayg").first()
        ray.contact_name = "Ray"
        t_roland, h_roland = updates.render(roland, secs[0])
        t_ray, h_ray = updates.render(ray, secs[0])
        assert "Hi Roland," in t_roland and "Hi Ray," in t_ray
        assert "jumping about" in t_roland and "jumping about" not in t_ray        # (Roland)-only line
        assert "back on your website" in t_ray and "back on your website" not in t_roland
        assert "(Roland)" not in h_roland and "<ul" in h_roland and "<strong>" in h_roland
    a = app.test_client()
    _login(a, "admin@test")
    page = a.get("/admin/updates?show=update").get_data(as_text=True)
    assert "Write a message" in page and "A few improvements" not in page          # draft kept off the tab


def test_dashboard_invite_friends_plan(app):
    import datetime as dt
    from models import db
    from models.core import Account, User
    from utils import updates
    from utils.plans import friends_end_default
    with app.test_request_context("/"):
        a = Account.query.filter_by(slug="rolands").first()
        owner = User.query.filter_by(account_id=a.id, role="owner").first()
        owner.is_active_flag = False
        db.session.commit()
        sec = updates.sections(updates.INVITE_FILE)[0]
        text, html = updates.page(a, sec)
        end = friends_end_default()
        assert "friends plan" in text.lower() and "£" not in text and "£" not in html
        assert "on our Friends plan" in html and "Open your dashboard" in html and owner.email in html
        assert "[[" not in text and "{" not in text
    ad = app.test_client()
    _login(ad, "admin@test")
    page = ad.get("/admin/updates?show=invite").get_data(as_text=True)
    assert "Dashboard invite" in page and "srcdoc=" in page
    n = len(_outbox(app))
    _form(ad, "/admin/updates", {"kind": "invite", "section": "0", "client": "rolands", "action": "test"}, page="/admin/updates")
    with app.app_context():                                     # a test changes nothing
        assert not User.query.filter_by(account_id=a.id, role="owner").first().is_active_flag
    _form(ad, "/admin/updates", {"kind": "invite", "section": "0", "client": "rolands", "action": "send"}, page="/admin/updates")
    outbox = _outbox(app)
    assert len(outbox) == n + 2 and "Your new HapiTech dashboard is ready" in outbox[-1]
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        assert User.query.filter_by(account_id=a.id, role="owner").first().is_active_flag
        assert a.addon().status == "friends" and a.addon().is_enabled and a.addon().trial_ends_at == end
        assert a.addon().renew_months == 3
        assert "Friends plan" in a.addon().plan["name"]
    assert "Sent" in ad.get("/admin/updates").get_data(as_text=True)
    o = app.test_client(); _login(o, owner_email := "roland@test")
    settings = o.get("/portal/settings").get_data(as_text=True)
    assert "on our Friends plan" in settings and "£" not in settings


def test_open_form_reviews_wait_unless_customer(app, monkeypatch):
    import datetime as dt
    import routes.reviews_public as rp
    from models import db
    from models.core import Account
    from models.reviews import Review
    from models.work import Lead
    from utils.tasks import run_all
    monkeypatch.setattr(rp, "MIN_SECONDS_TO_WRITE", 0)
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.contact_email = "owner@test"
        db.session.add(Lead(account_id=a.id, name="Real Customer", email="real@example.com", status="done"))
        db.session.commit()
    def post(name, email):
        c = app.test_client()
        html = c.get("/reviews/rolands/write").get_data(as_text=True)
        tok = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        t = re.search(r'name="t" value="([^"]+)"', html).group(1)
        return c.post("/reviews/rolands/write", data={"csrf_token": tok, "t": t, "rating": "5", "name": name,
                                                       "body": "Great", "email": email})
    assert "once Roland has seen it" in post("Stranger", "who@example.com").get_data(as_text=True)
    post("Real", "REAL@example.com")
    with app.app_context():
        s = Review.query.filter_by(author_name="Stranger").first()
        r = Review.query.filter_by(author_name="Real").first()
        assert s.status == "pending" and not s.verified
        assert r.status == "published" and r.verified
    assert any("waiting for your OK" in m for m in _outbox(app))
    assert "Stranger" not in app.test_client().get("/reviews/rolands").get_data(as_text=True)   # not public yet
    o = app.test_client()
    _login(o, "roland@test")
    page = o.get("/portal/reviews").get_data(as_text=True)
    assert "Waiting for your OK (1)" in page
    with app.app_context():
        sid = Review.query.filter_by(author_name="Stranger").first().id
    _form(o, f"/portal/reviews/{sid}", {"action": "approve"}, page="/portal/reviews")
    with app.app_context():
        assert db.session.get(Review, sid).status == "published"
        # an untouched one goes live after 14 days
        old = Review(account_id=Account.query.filter_by(slug="rolands").first().id, author_name="Old", rating=3,
                     status="pending", source="website", created_at=dt.datetime.utcnow() - dt.timedelta(days=15))
        db.session.add(old); db.session.commit(); oid = old.id
    assert run_all(app, force=True)["auto_published"] == 1
    with app.app_context():
        assert db.session.get(Review, oid).status == "published"


def test_publish_post_shows_share_card_and_home_tips(app):
    o = app.test_client()
    _login(o, "roland@test")
    r = _form(o, "/portal/posts/new", {"title": "New bathroom in Tettenhall", "town": "Tettenhall",
                                       "body": "Four days.", "action": "publish"}, page="/portal/posts/new")
    assert r.status_code == 302 and r.headers["Location"].endswith("#share")
    page = o.get(r.headers["Location"].split("#")[0]).get_data(as_text=True)
    assert "Share it" in page and "facebook.com/sharer" in page and "/posts/" in page
    home = o.get("/portal/").get_data(as_text=True)
    assert "Edit my website" in home and "tip__text" in home and "Latest reviews" not in home
    assert "Visitors" in o.get("/portal/visitors").get_data(as_text=True)


def test_owner_adds_review_and_google_link_opens_reviews_page(app):
    from models import db
    from models.core import Account
    from models.reviews import Review
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.google_profile_url, a.google_reviews_url = "https://g.page/r/X/review", "https://www.google.com/search?q=Rolands+Reviews"
        db.session.commit()
    o = app.test_client()
    _login(o, "roland@test")
    page = o.get("/portal/reviews/add").get_data(as_text=True)
    assert "Waiting on Google API access" in page and 'value="google"' in page
    r = _form(o, "/portal/reviews/add", {"source": "google", "rating": "5", "author_name": "Jo Bloggs",
                                         "body": "Brilliant job"}, page="/portal/reviews/add")
    assert r.status_code == 302
    with app.app_context():
        rv = Review.query.filter_by(author_name="Jo Bloggs").first()
        assert rv.source == "google" and rv.status == "published"
        assert rv.link == "https://www.google.com/search?q=Rolands+Reviews"     # not the write-a-review form
    assert "https://www.google.com/search?q=Rolands+Reviews" in o.get("/portal/reviews").get_data(as_text=True)
    data = app.test_client().get("/api/v1/sites/rolands/reviews", headers=_site_key(app, "rolands")).json
    jo = next(x for x in data["reviews"] if x["name"] == "Jo Bloggs")
    assert jo["source_url"] == "https://www.google.com/search?q=Rolands+Reviews"


def test_post_photos_go_into_gallery_and_leave_with_the_post(app):
    import json as _json
    from models import db
    from models.core import Account
    from models.content import ContentBlock, Post
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        orig = _json.dumps(["static:img/gallery/a.jpg"])
        db.session.add(ContentBlock(account_id=a.id, key="photos.gallery", type="images", label="Gallery photos",
                                    group="Photos", value=orig, default_value=orig))
        db.session.commit()
    o = app.test_client()
    _login(o, "roland@test")
    r = _form(o, "/portal/posts/new", {"title": "Shed in Codsall", "action": "publish", "to_gallery": "1",
                                       "photos": (_png(), "shed.png")}, page="/portal/posts/new",
              content_type="multipart/form-data")
    assert r.status_code == 302
    with app.app_context():
        p = Post.query.filter_by(title="Shed in Codsall").first()
        g_ = ContentBlock.query.filter_by(key="photos.gallery").first()
        assert g_.data[0] == p.photo_id_list[0] and g_.data[1] == "static:img/gallery/a.jpg"   # newest first
        pid = p.id
    _form(o, f"/portal/posts/{pid}", {"action": "delete"}, page=f"/portal/posts/{pid}")
    with app.app_context():
        g_ = ContentBlock.query.filter_by(key="photos.gallery").first()
        assert g_.data == ["static:img/gallery/a.jpg"]
        assert all("static:img/gallery/a.jpg" in v.value and v.value.count(",") == 0 for v in g_.versions)


def test_review_age_and_admin_sets_date(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.reviews import Review
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        r = Review(account_id=a.id, source="google", author_name="Dated", rating=5, body="ok", status="published")
        db.session.add(r); db.session.commit(); rid = r.id
        f = app.jinja_env.filters["age"]
        today = dt.date.today()
        assert [f(today), f(today - dt.timedelta(days=1)), f(today - dt.timedelta(days=5)),
                f(today - dt.timedelta(days=22)), f(today - dt.timedelta(days=95)), f(today - dt.timedelta(days=800))] == \
               ["today", "yesterday", "5 days ago", "3 weeks ago", "3 months ago", "2 years ago"]
    ad = app.test_client()
    _login(ad, "admin@test")
    assert "no date" in ad.get("/admin/reviews?status=all").get_data(as_text=True)
    when = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    _form(ad, f"/admin/reviews/{rid}", {"action": "date", "reviewed_at": when}, page="/admin/reviews")
    with app.app_context():
        assert db.session.get(Review, rid).reviewed_at.date().isoformat() == when
    o = app.test_client(); _login(o, "roland@test")
    assert "2 weeks ago" in o.get("/portal/reviews").get_data(as_text=True)


def test_website_editor_cards_save_in_place(app):
    import json as _json
    from models import db
    from models.core import Account
    from models.content import ContentBlock
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        t = ContentBlock(account_id=a.id, key="services.wall.title", type="text", label="Wall: heading", group="Services",
                         value=_json.dumps("Wall Mounting"), default_value=_json.dumps("Wall Mounting"), max_length=60)
        d = ContentBlock(account_id=a.id, key="services.wall.intro", type="longtext", label="Wall: intro", group="Services",
                         value=_json.dumps("TVs and shelves."), default_value=_json.dumps("TVs and shelves."), max_length=400)
        db.session.add_all([t, d]); db.session.commit(); tid, did = t.id, d.id
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/website").get_data(as_text=True)
    assert "data-site-edit" in page and page.count(f'name="b{tid}"') == 1 and f'name="b{did}"' in page   # one card, both fields
    r = _form(o, "/portal/website/save", {f"b{tid}": "Wall Mounting & Shelves", f"b{did}": "TVs and shelves."}, page="/portal/website")
    assert r.status_code == 302 and r.headers["Location"].endswith(f"#b{tid}")
    with app.app_context():
        assert db.session.get(ContentBlock, tid).data == "Wall Mounting & Shelves"
        assert db.session.get(ContentBlock, did).is_default                    # unchanged field untouched
        assert len(db.session.get(ContentBlock, tid).versions) == 1          # undo still works
    _form(o, "/portal/website/save", {f"b{tid}": "x" * 61}, page="/portal/website")
    with app.app_context():
        assert db.session.get(ContentBlock, tid).data == "Wall Mounting & Shelves"   # too long: rejected



def test_friends_plan_renews_and_can_be_switched(app):
    import datetime as dt
    from models import db
    from models.core import Account, AddOn
    from utils.plans import roll_forward
    from utils.tasks import run_all
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        ad = a.addon() or AddOn(account_id=a.id)
        ad.status, ad.trial_ends_at, ad.renew_months = "friends", dt.date.today() - dt.timedelta(days=1), 3
        db.session.add(ad); db.session.commit()
        assert ad.is_enabled                                         # auto-renewing never lapses
    assert run_all(app, force=True)["friends_renewed"] == 1
    with app.app_context():
        ad = Account.query.filter_by(slug="rolands").first().addon()
        assert ad.trial_ends_at > dt.date.today()
        ad.renew_months, ad.trial_ends_at = None, dt.date.today() - dt.timedelta(days=1)
        db.session.commit()
        assert not ad.is_enabled and not roll_forward(ad)           # renew off: it ends
    adm = app.test_client(); _login(adm, "admin@test")
    until = (dt.date.today() + dt.timedelta(days=40)).isoformat()
    _form(adm, "/admin/clients/rolands/addon", {"status": "friends", "until": until, "renew_months": "6"}, page="/admin/clients/rolands")
    with app.app_context():
        ad = Account.query.filter_by(slug="rolands").first().addon()
        assert ad.trial_ends_at.isoformat() == until and ad.renew_months is None    # box unticked
    _form(adm, "/admin/clients/rolands/addon", {"status": "friends", "until": until, "renew": "1", "renew_months": "6"}, page="/admin/clients/rolands")
    with app.app_context():
        assert Account.query.filter_by(slug="rolands").first().addon().renew_months == 6
    assert "Auto-renew every" in adm.get("/admin/clients/rolands").get_data(as_text=True)


def test_invite_someone_new(app):
    from models.core import Account, User
    adm = app.test_client(); _login(adm, "admin@test")
    r = _form(adm, "/admin/updates/new", {"business": "Smith Plumbing", "contact_name": "Dave Smith",
                                          "email": "Dave@Smith.test", "domain": "https://smithplumbing.co.uk/"}, page="/admin/updates")
    assert r.status_code == 302
    with app.app_context():
        a = Account.query.filter_by(slug="smith-plumbing").first()
        u = User.query.filter_by(email="dave@smith.test").first()
        assert a and a.domain == "smithplumbing.co.uk" and u.account_id == a.id and not u.is_active_flag
    page = adm.get("/admin/updates?show=new").get_data(as_text=True)
    assert 'id="c-smith-plumbing"' in page and "Hi Dave" in page
    assert 'id="c-smith-plumbing"' not in adm.get("/admin/updates?show=invite").get_data(as_text=True)
    _form(adm, "/admin/updates", {"kind": "invite", "section": "0", "client": "smith-plumbing", "action": "send"}, page="/admin/updates")
    with app.app_context():
        assert User.query.filter_by(email="dave@smith.test").first().is_active_flag
        assert Account.query.filter_by(slug="smith-plumbing").first().addon().status == "friends"
    assert any("dave@smith.test" in m and "Your new HapiTech dashboard" in m for m in _outbox(app))
    dup = _form(adm, "/admin/updates/new", {"business": "Other", "email": "dave@smith.test"}, page="/admin/updates")
    with app.app_context():
        assert not Account.query.filter_by(name="Other").first()


def test_spam_enquiries_kept_out_of_jobs(app):
    import datetime as dt
    from models import db
    from models.work import Lead
    from utils.tasks import run_all
    key = _site_key(app, "rolands")
    c = app.test_client()
    real = c.post("/api/v1/sites/rolands/enquiries", json={"name": "Jane", "message": "Shelves please"}, headers=key)
    spam = c.post("/api/v1/sites/rolands/enquiries", headers=key, json={
        "name": "Garland", "message": 'No verification payid casino <a href="https://x.example">here</a>'})
    assert real.status_code == spam.status_code == 201
    with app.app_context():
        assert db.session.get(Lead, spam.json["id"]).status == "spam"
        assert db.session.get(Lead, real.json["id"]).status == "new"
    o = app.test_client(); _login(o, "roland@test")
    jobs = o.get("/portal/jobs").get_data(as_text=True)
    assert "Jane" in jobs and "Garland" not in jobs
    page = o.get(f"/portal/jobs/{real.json['id']}").get_data(as_text=True)
    assert "It's spam" in page
    adm = app.test_client(); _login(adm, "admin@test")
    assert "Garland" not in adm.get("/admin/work?show=all").get_data(as_text=True)
    assert "Garland" in adm.get("/admin/work?show=spam").get_data(as_text=True)
    with app.app_context():
        db.session.get(Lead, spam.json["id"]).created_at = dt.datetime.utcnow() - dt.timedelta(days=15)
        db.session.commit()
    assert run_all(app, force=True)["spam_deleted"] == 1


def test_hapitech_own_updates_and_reviews(app, monkeypatch):
    import routes.reviews_public as rp
    from models.reviews import Review
    monkeypatch.setattr(rp, "MIN_SECONDS_TO_WRITE", 0)
    adm = app.test_client(); _login(adm, "admin@test")
    r = adm.get("/admin/me/post")
    assert r.status_code == 302 and r.headers["Location"].endswith("/portal/posts/new")
    r = _form(adm, "/portal/posts/new", {"title": "New site for a local plumber", "body": "Launched today.",
                                         "action": "publish"}, page="/portal/posts/new")
    pid = int(r.headers["Location"].split("/portal/posts/")[1].split("#")[0])
    share = adm.get(f"/portal/posts/{pid}").get_data(as_text=True)
    assert f"https://hapitech.dev/posts/{pid}" in share or "hapitech.dev%2Fposts%2F" in share
    pub = app.test_client()
    assert "New site for a local plumber" in pub.get("/updates").get_data(as_text=True)
    one = pub.get(f"/updates/{pid}").get_data(as_text=True)
    assert 'property="og:title" content="New site for a local plumber"' in one
    assert pub.get(f"/posts/{pid}").headers["Location"].endswith(f"/updates/{pid}")
    assert "What we've been up to" in pub.get("/").get_data(as_text=True)
    # Roland reviews HapiTech with his login email: verified, straight onto the homepage
    html = pub.get("/reviews/hapitech/write").get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
    t = re.search(r'name="t" value="([^"]+)"', html).group(1)
    pub.post("/reviews/hapitech/write", data={"csrf_token": tok, "t": t, "rating": "5", "name": "Roland",
                                               "body": "Aaron built my site", "email": "roland@test"})
    with app.app_context():
        rv = Review.query.filter_by(author_name="Roland", body="Aaron built my site").first()
        assert rv.verified and rv.status == "published"
    home = pub.get("/").get_data(as_text=True)
    assert "What clients say" in home and "Aaron built my site" in home
    assert "My reviews" in adm.get("/admin/").get_data(as_text=True)


def test_finances_nav_order_brand_and_website_button(app):
    from models import db
    from models.core import Account
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.brand_colour, a.domain = "#f97316", "rolandshandyman.co.uk"
        db.session.commit()
    o = app.test_client(); _login(o, "roland@test")
    assert o.get("/portal/finances").headers["Location"].endswith("/portal/plan")
    fin = o.get("/portal/plan").get_data(as_text=True)
    assert "£0.00" in fin and "all square" in fin
    home = o.get("/portal/").get_data(as_text=True)
    side = home[home.index('class="side__nav"'):home.index("</nav>", home.index('class="side__nav"'))]
    order = [label for label in ("Home", "My website", "Visitors", "Reviews", "Posts", "Jobs", "Calendar", "My plan", "Settings", "Help")
             if f"<span>{label}</span>" in side]
    positions = [side.index(f"<span>{label}</span>") for label in order]
    assert len(order) == 10 and positions == sorted(positions) and "Ask for a review</span>" not in side
    assert 'href="https://rolandshandyman.co.uk" target="_blank"' in home          # Website button -> their site
    assert ':root[data-accent="brand"]{--acc:#f97316' in home
    tabbar = home[home.index('class="tabbar"'):]
    assert tabbar.index("Home") < tabbar.index("Jobs") < tabbar.index("Ask") < tabbar.index("Reviews")
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, "/admin/clients/rolands/edit", {"name": "Roland's Handyman", "balance_gbp": "45.50",
                                               "billing_note": "Hosting for December"}, page="/admin/clients/rolands/edit")
    fin = o.get("/portal/plan").get_data(as_text=True)
    assert "£45.50" in fin and "Hosting for December" in fin
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().brand_colour = "red;}body{display:none"
        db.session.commit()
    assert "display:none" not in o.get("/portal/").get_data(as_text=True)            # only #rrggbb gets into CSS



def test_write_a_message_to_clients(app):
    from models.core import Note
    adm = app.test_client(); _login(adm, "admin@test")
    page = adm.get("/admin/updates").get_data(as_text=True)
    assert "Write a message" in page and page.index(">What's new<") < page.index(">Dashboard invite<")
    body = "Hi {name},\n\nQuick note: **new features** are live.\n\n- Visitors page\n- Finances page\n\nThanks,\nAaron"
    prev = adm.post("/admin/updates", data={"kind": "message", "subject": "Small update", "body": body, "to": ["rolands"],
                                            "action": "preview", "csrf_token": _csrf(adm, "/admin/updates")})
    html = prev.get_data(as_text=True)
    assert "Preview for Roland" in html and "Hi Roland," in html
    n = len(_outbox(app))
    _form(adm, "/admin/updates", {"kind": "message", "subject": "Small update", "body": body, "to": ["rolands", "rayg"],
                                  "action": "send"}, page="/admin/updates")
    out = _outbox(app)[n:]
    assert len(out) == 2 and any("Hi Roland," in m for m in out) and any("Hi Ray" in m for m in out)
    with app.app_context():
        assert Note.query.filter_by(body="Message emailed: Small update").count() == 2
    assert "Sent messages (2)" in adm.get("/admin/updates").get_data(as_text=True)


def test_report_an_issue(app):
    from models.work import Lead
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/jobs").get_data(as_text=True)
    assert "Report an issue with this page" in page
    tok = _csrf(o, "/portal/jobs")
    n = len(_outbox(app))
    r = o.post("/portal/issue", headers={"X-CSRF-Token": tok}, json={
        "what": "Save button does nothing", "on_before": True, "page": "/portal/help", "before": "/portal/website/3",
        "device": "iPhone Safari", "screen": "390x844"})
    assert r.json["ok"]
    with app.app_context():
        lead = Lead.query.filter_by(source="issue").first()
        assert lead.account.slug == "hapitech" and lead.title == "Issue on /portal/website/3"
        assert "Save button does nothing" in lead.message and "iPhone Safari" in lead.message
    mail = _outbox(app)[n:]
    assert len(mail) == 1 and "aaron@hapitech.dev" in mail[0] and "Save button does nothing" in mail[0]
    assert o.post("/portal/issue", headers={"X-CSRF-Token": tok}, json={"what": ""}).status_code == 400
    adm = app.test_client(); _login(adm, "admin@test")
    home = adm.get("/admin/").get_data(as_text=True)
    assert "Reported issues" in home
    adm.get("/admin/me/jobs")
    assert "Roland" in adm.get("/portal/jobs").get_data(as_text=True)
    # Roland's own Jobs never shows it
    assert "Save button does nothing" not in o.get("/portal/jobs").get_data(as_text=True)



def test_my_plan_value_running_costs_and_support_button(app):
    import datetime as dt
    from models import db
    from models.core import Account, AddOn, Job, Payment, RunningCost
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        start = dt.date.today() - dt.timedelta(days=365)
        db.session.add_all([
            Job(account_id=a.id, title="Website creation", type="build", status="done", price_gbp=300, due_date=start),
            Job(account_id=a.id, title="Server setup", type="hosting", status="done", price_gbp=200, due_date=start),
            Payment(account_id=a.id, amount_gbp=500, paid_at=start),
            RunningCost(account_id=a.id, title="Server hosting", kind="hosting", value_gbp=29.99, my_cost_gbp=40,
                        interval="monthly", started_on=start, covered=True),
            RunningCost(account_id=a.id, title="Email", kind="email", value_gbp=25, my_cost_gbp=25, interval="yearly",
                        started_on=start, covered=True)])
        ad = a.addon() or AddOn(account_id=a.id)
        ad.status, ad.renew_months = "friends", 3
        db.session.add(ad); db.session.commit()
        from utils.plan_value import summary
        v = summary(a)
        assert v["work_total"] == 500 and v["paid"] == 500
        tx = [t for t in v["transactions"] if not t["upcoming"]]
        assert len(tx) == 13                                   # a charge each month for 13 months (start + 12)
        first = tx[-1]
        assert first["summary"].startswith("Website build & launch") and first["paid"] == 500 and first["status"] == "Paid"
        assert round(v["saved"], 2) == round(13 * 29.99 + 2 * 25, 2)   # hosting monthly + email at start and at 1 year
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/plan").get_data(as_text=True)
    assert "Saved on this plan" in page and "Transaction history" in page and "Friends plan: Server hosting" in page
    assert page.index("Transaction history") < page.index("Saved on this plan") and "💛" not in page and "😎" in page
    ref = re.search(r'/portal/plan/(HT-[\d-]+)"', page).group(1)
    rc = o.get(f"/portal/plan/{ref}").get_data(as_text=True)
    assert "Download PDF" in rc and ref in rc and "Friends plan" in rc
    assert o.get("/portal/plan/HT-999-20200101").status_code == 404
    assert "Support HapiTech" not in page                                          # no link set yet (clients)
    assert "£40" not in page                                                        # HapiTech's own cost stays private
    adm = app.test_client(); _login(adm, "admin@test")
    adm.get("/admin/clients/rolands/portal")
    assert "Layout preview" in adm.get("/portal/plan").get_data(as_text=True)                   # admin sees a preview
    _form(adm, "/admin/settings", {"action": "donate", "donate_url": "https://paypal.me/hapitech"}, page="/admin/settings")
    assert "Support HapiTech" in o.get("/portal/plan").get_data(as_text=True)
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().addon().status = "active"
        db.session.commit()
    assert "Support HapiTech" not in o.get("/portal/plan").get_data(as_text=True)  # Friends plan only
    money = adm.get("/admin/clients/rolands?tab=money").get_data(as_text=True)
    assert "Running costs" in money and "costs you £40.00" in money
    _form(adm, "/admin/clients/rolands/costs", {"title": "Domain renewal", "kind": "domain", "value_gbp": "12",
                                                "interval": "yearly", "covered": "1"}, page="/admin/clients/rolands")
    with app.app_context():
        assert RunningCost.query.filter_by(title="Domain renewal").first().covered


def test_language_switch_on_client_dashboard_only(app):
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/").get_data(as_text=True)
    assert 'data-lang="lv"' in page and "i18n-lv.js" in page and "lv-pending" in page
    adm = app.test_client(); _login(adm, "admin@test")
    assert 'data-lang="lv"' not in adm.get("/admin/").get_data(as_text=True)
    js = app.test_client().get("/static/js/i18n-lv.js").get_data(as_text=True)
    assert '"My plan": "Mans plāns"' in js and '"Saved on this plan": "Ietaupīts ar šo plānu"' in js
