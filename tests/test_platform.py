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
PORTAL_PAGES = ["/portal/", "/portal/visitors", "/portal/website/hero", "/portal/ask", "/portal/reviews?show=sent", "/portal/reviews", "/portal/posts", "/portal/posts/new", "/portal/jobs", "/portal/jobs/new", "/portal/calendar", "/portal/settings",
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
    assert data["name"] == "Roland's Handyman" and data["start_url"] == "/portal/?app=rolands" and "HapiTech" not in data["name"]
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
        assert ensure_blocks(a, None) == 45
        db.session.commit()
        assert ensure_blocks(a, None) == 0                     # idempotent
        assert ContentBlock.query.filter_by(account_id=a.id, key="services.wall.title").first().data == "Wall Mounting Service"
        order = [b.key for b in ContentBlock.query.filter_by(account_id=a.id).order_by(ContentBlock.sort).all()]
        assert order[0] == "hero.title" and order[-1] == "legal.terms.page" and order.index("area.title") > order.index("services.plumbing.title")
        acc = ContentBlock.query.filter_by(account_id=a.id, key="services.furniture.acc2.text").first()
        assert acc.data.startswith("✔ Personally assembled by Rolands\n✔")
    # the dashboard's list and the site's own defaults must be the same file
    import json, os
    site = os.path.join(app.root_path, "..", "clients", "rolandshandyman.co.uk", "static", "hapitech", "blocks.json")
    if os.path.exists(site):
        mine = json.load(open(os.path.join(app.root_path, "utils", "site_blocks", "rolandshandyman.co.uk.json")))
        assert json.load(open(site)) == mine


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
        secs = updates.sections("docs/client-updates.md")
        assert secs and secs[0]["title"]
        roland = Account.query.filter_by(slug="rolands").first()
        ray = Account.query.filter_by(slug="rayg").first()
        ray.contact_name = "Ray"
        t_roland, h_roland = updates.render(roland, secs[0])
        t_ray, h_ray = updates.render(ray, secs[0])
        assert "Hi Roland," in t_roland and "Hi Ray," in t_ray
        assert "jumps about" in t_roland and "jumps about" not in t_ray            # (Roland)-only line
        assert "photos are back" in t_ray and "photos are back" not in t_roland
        assert "(Roland)" not in h_roland and "<ul" in h_roland and "<strong>" in h_roland
    a = app.test_client()
    _login(a, "admin@test")
    page = a.get("/admin/updates?show=update").get_data(as_text=True)
    assert "Write a message" in page and "Everything that&#39;s new" in page


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
    assert "Share it" in page and "/posts/" in page
    assert page.index('data-share-to="facebook"') < page.index('data-share-to="instagram"') < page.index('data-share-to="whatsapp"')   # Facebook, Instagram first
    home = o.get("/portal/").get_data(as_text=True)
    assert "Edit my website" in home and "tipbar__text" in home and "Latest reviews" not in home
    assert "Visitors" in o.get("/portal/visitors").get_data(as_text=True)


def test_owner_adds_review_and_google_link_opens_reviews_page(app):
    from models import db
    from models.core import Account
    from models.reviews import Review
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.google_profile_url, a.google_reviews_url = "https://g.page/r/X/review", "https://www.google.com/search?q=Rolands+Reviews"
        db.session.commit()
    owner = app.test_client()
    _login(owner, "roland@test")
    assert owner.get("/portal/reviews/add").status_code == 302                  # clients can't add reviews by hand
    assert "/portal/reviews/add" not in owner.get("/portal/reviews").get_data(as_text=True)
    assert "/portal/ask" in owner.get("/portal/reviews").get_data(as_text=True)
    o = app.test_client()
    _login(o, "admin@test")
    page = o.get("/portal/reviews/add?as=rolands").get_data(as_text=True)
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
    assert "Enquiries &amp; jobs" in home and "side__badge" in home      # issues land in your own Jobs
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
    assert "data-support-open" not in page                                          # no options set yet
    assert "£40" not in page                                                        # HapiTech's own cost stays private
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, "/admin/settings", {"action": "support", "support_paypal": "aaron@hapitech.dev",
                                   "support_revolut": "https://checkout.revolut.com/pay/test"}, page="/admin/settings")
    page = o.get("/portal/plan").get_data(as_text=True)
    assert "data-support-open" in page and "paypal.com/donate/?business=aaron%40hapitech.dev" in page
    assert "checkout.revolut.com/pay/test" in page and page.index("Saved on this plan") < page.index("data-support-open")
    n = len(_outbox(app))
    r = o.post("/portal/support", json={"method": "revolut", "amount": "10"}, headers={"X-CSRF-Token": _csrf(o, "/portal/plan")})
    assert r.json["ok"]
    from models.core import Note
    with app.app_context():
        assert Note.query.filter_by(body="Support HapiTech: chose Revolut (£10)").count() == 1
    mail = _outbox(app)[n:]
    assert len(mail) == 1 and "aaron@hapitech.dev" in mail[0] and "Revolut" in mail[0]
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().addon().status = "active"
        db.session.commit()
    assert "data-support-open" not in o.get("/portal/plan").get_data(as_text=True)  # Friends plan only
    money = adm.get("/admin/clients/rolands?tab=money").get_data(as_text=True)
    assert "Running costs" in money and "£40.00" in money and "History" in money and "+ Record a payment" in money
    _form(adm, "/admin/clients/rolands/costs", {"title": "Domain renewal", "kind": "domain", "value_gbp": "12",
                                                "interval": "yearly", "covered": "1"}, page="/admin/clients/rolands")
    with app.app_context():
        assert RunningCost.query.filter_by(title="Domain renewal").first().covered


def test_language_switch_on_client_dashboard_only(app):
    from models import db
    from models.core import Account
    o = app.test_client(); _login(o, "roland@test")
    assert 'data-lang="lv"' not in o.get("/portal/").get_data(as_text=True)        # English only unless switched on
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().languages = "lv"; db.session.commit()
    page = o.get("/portal/").get_data(as_text=True)
    assert 'data-lang="lv"' in page and "i18n-lv.js" in page and "lv-pending" in page
    ray = app.test_client(); _login(ray, "ray@test")
    assert 'data-lang="lv"' not in ray.get("/portal/").get_data(as_text=True)
    adm = app.test_client(); _login(adm, "admin@test")
    assert 'data-lang="lv"' not in adm.get("/admin/").get_data(as_text=True)
    js = app.test_client().get("/static/js/i18n-lv.js").get_data(as_text=True)
    assert '"My plan": "Mans plāns"' in js and '"Saved on this plan": "Ietaupīts ar šo plānu"' in js


def test_installed_app_opens_client_dashboard_and_logs_in_inside_the_app(app):
    import json as _json
    c = app.test_client()
    m = _json.loads(c.get("/app/rolands/manifest.webmanifest").get_data(as_text=True))
    assert m["start_url"] == "/portal/?app=rolands" and m["scope"] == "/portal/"
    r = c.get("/portal/?app=rolands")                                   # logged out: the app's own login
    assert r.status_code == 302 and "/portal/login?app=rolands" in r.headers["Location"]
    page = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Log in" in page and "Roland" in page and "/app/rolands/icon-192.png" in page and 'data-next="/portal/' in page
    tok = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
    code = c.post("/auth/code/request", json={"email": "roland@test"}, headers={"X-CSRF-Token": tok}).json["dev_code"]
    v = c.post("/auth/code/verify?next=/portal/?app=rolands", json={"code": code, "remember": True}, headers={"X-CSRF-Token": tok})
    assert v.json["ok"] and v.json["redirect"].startswith("/portal/")
    home = c.get("/portal/?app=rolands")
    assert home.status_code == 200 and "ht_app=rolands" in (home.headers.get("Set-Cookie") or "") or "ht_app" in c.get_cookie("ht_app").key
    out = c.post("/logout", data={"csrf_token": _csrf(c, "/portal/"), "next": "/portal/login?app=rolands"})
    assert out.headers["Location"].endswith("/portal/login?app=rolands")
    assert "/portal/login" in c.get("/portal/").headers["Location"]           # remembers whose app it is


def test_needs_attention_counts_payments_across_order_stages(app):
    from models import db
    from models.core import Account, Job, Payment
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        j1 = Job(account_id=a.id, title="Website creation", status="done", price_gbp=300)
        j2 = Job(account_id=a.id, title="Server setup", status="done", price_gbp=200)
        db.session.add_all([j1, j2]); db.session.flush()
        db.session.add(Payment(account_id=a.id, job_id=j1.id, amount_gbp=500))
        db.session.commit()
    adm = app.test_client(); _login(adm, "admin@test")
    assert "unpaid</span>" not in adm.get("/admin/").get_data(as_text=True)


def test_work_request_with_and_without_offer(app):
    from models.work import Lead
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/plan").get_data(as_text=True)
    assert "Need something doing?" in page and "data-work-open" in page
    n = len(_outbox(app))
    _form(o, "/portal/requests/work", {"kind": "feature", "what": "Add a kitchen fitting page", "offer": "£150"}, page="/portal/plan")
    _form(o, "/portal/requests/work", {"kind": "change", "what": "New phone number on the site", "offer": ""}, page="/portal/plan")
    with app.app_context():
        reqs = Lead.query.filter_by(source="request").order_by(Lead.id).all()
        assert len(reqs) == 2 and reqs[0].account.slug == "hapitech" and reqs[0].for_account.slug == "rolands"
        assert float(reqs[0].offer_gbp) == 150 and reqs[1].offer_gbp is None
        assert reqs[0].title == "A new feature or page: Add a kitchen fitting page"
        rid = reqs[0].id
    assert len(_outbox(app)) == n + 2
    page = o.get("/portal/plan").get_data(as_text=True)
    assert "Add a kitchen fitting page" in page and "you offered £150.00" in page and "Received" in page
    adm = app.test_client(); _login(adm, "admin@test")
    adm.get("/admin/me/jobs")
    job = adm.get(f"/portal/jobs/{rid}").get_data(as_text=True)
    assert "They offered:" in job and "Roland" in job


def test_site_enquiry_becomes_a_client_with_a_project_page(app):
    from models.core import Account, User
    from models.work import Lead
    c = app.test_client()
    tok = _csrf(c, "/")
    r = c.post("/contact", headers={"X-CSRF-Token": tok}, json={
        "name": "Dave Smith", "email": "dave@smithplumbing.test", "message": "Looking for: A website\\n\\nNeed a site",
        "business": "Smith Plumbing", "phone": "07700900111", "need": "A website"})
    c.post("/contact", headers={"X-CSRF-Token": tok}, json={"name": "Spam", "email": "x@y.z",
        "message": 'casino payid <a href="https://x.example">win</a>'})
    with app.app_context():
        lead = Lead.query.filter_by(source="enquiry", name="Dave Smith").first()
        assert lead and lead.account.slug == "hapitech" and lead.title == "A website for Smith Plumbing"
        assert Lead.query.filter_by(source="enquiry", name="Spam").first().status == "spam"
        lid = lead.id
    adm = app.test_client(); _login(adm, "admin@test")
    adm.get("/admin/me/jobs")
    assert "Make them a client" in adm.get(f"/portal/jobs/{lid}").get_data(as_text=True)
    r = _form(adm, f"/portal/jobs/{lid}", {"action": "make-client"}, page=f"/portal/jobs/{lid}")
    assert r.headers["Location"].endswith("/admin/clients/smith-plumbing")
    with app.app_context():
        acc = Account.query.filter_by(slug="smith-plumbing").first()
        u = User.query.filter_by(email="dave@smithplumbing.test").first()
        assert acc.contact_phone == "07700900111" and u.account_id == acc.id and not u.is_active_flag
        assert Lead.query.get(lid).for_account_id == acc.id
    assert 'id="c-smith-plumbing"' in adm.get("/admin/updates?show=new").get_data(as_text=True)
    _form(adm, "/admin/updates", {"kind": "invite", "section": "0", "client": "smith-plumbing", "action": "send"}, page="/admin/updates")
    adm.get("/admin/clients/smith-plumbing/portal")
    site = adm.get("/portal/website").get_data(as_text=True)
    assert "Your new website is on its way" in site and "Your website project" in site


SAMPLE_GOOGLE = """Lamia Rouibah
4 reviews
2 weeks agoNew
Reasonable price
Rolands did an amazing job fixing my wardrobe. … More
Mohammad Zaheer
8 reviews·2 photos
7 months ago
First time I used Roland.
Photo 1 in review by Mohammad Zaheer
Photo 2 in review by Mohammad Zaheer
Rolands Handyman (owner)
7 months ago
“Really appreciate it!
Thanks”
Gertrude Murekeyisoni
10 months ago
Rolands Handyman (owner)
10 months ago
Thank you.
"""


def test_google_copy_import_and_reviews_site(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.reviews import Review
    from utils.review_import import import_google, parse
    rows = parse(SAMPLE_GOOGLE, dt.date(2026, 11, 23))
    assert [r["name"] for r in rows] == ["Lamia Rouibah", "Mohammad Zaheer", "Gertrude Murekeyisoni"]
    assert rows[0]["date"] == dt.date(2026, 11, 9) and rows[0]["price"] == "Reasonable price" and rows[0]["body"].endswith("…")
    assert rows[1]["photos"] == 2 and rows[1]["reply"] == "Really appreciate it!\nThanks" and rows[1]["date"] == dt.date(2026, 4, 23)
    assert rows[2]["body"] == "" and rows[2]["reply"] == "Thank you."
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.google_reviews_url = "https://www.google.com/search?q=Rolands"
        db.session.commit()
        res = import_google(a, SAMPLE_GOOGLE, dt.date(2026, 11, 23))
        assert len(res["added"]) == 3
        assert len(import_google(a, SAMPLE_GOOGLE, dt.date(2026, 11, 23))["added"]) == 0      # safe to re-run
        mz = Review.query.filter_by(author_name="Mohammad Zaheer").first()
        assert mz.reply.body.startswith("Really") and mz.photo_count == 2 and mz.external and mz.rating == 5
        mzid = mz.id
    # client can't edit a Google reply
    o = app.test_client(); _login(o, "roland@test")
    page = o.get("/portal/reviews").get_data(as_text=True)
    assert "Your reply is on Google" in page and "📷 2 photos on Google" in page
    _form(o, f"/portal/reviews/{mzid}", {"action": "reply", "body": "changed"}, page="/portal/reviews")
    with app.app_context():
        assert Review.query.get(mzid).reply.body.startswith("Really")
    # the public reviews site
    pub = app.test_client()
    home = pub.get("/rv/").get_data(as_text=True)
    assert "One honest home" in home and "Roland" in home and "Where the reviews come from" in home
    biz = pub.get("/rv/rolands").get_data(as_text=True)
    assert "Mohammad Zaheer" in biz and "Reply from" in biz and "Read it all on Google" in biz and "Leave a review" in biz
    assert pub.get("/reviews/rolands").get_data(as_text=True) == biz                       # same page at the old address
    assert "nothing genuine" in pub.get("/rv/policy").get_data(as_text=True).lower() or "don't delete genuine" in pub.get("/rv/policy").get_data(as_text=True)
    # hapitech.report serves it at the root
    rep = pub.get("/rolands", base_url="https://hapitech.report")
    assert rep.status_code == 200 and "Mohammad Zaheer" in rep.get_data(as_text=True)
    assert 'href="/policy"' in pub.get("/", base_url="https://hapitech.report").get_data(as_text=True)
    # report a review -> stays up, Aaron's jobs + email
    n = len(_outbox(app))
    tok = _csrf(pub, "/rv/rolands")
    r = pub.post(f"/rv/report/{mzid}", json={"reason": "Wrong business", "details": "Not Roland", "email": ""}, headers={"X-CSRF-Token": tok})
    assert r.json["ok"]
    with app.app_context():
        from models.work import Lead
        assert Review.query.get(mzid).status == "reported"
        assert Lead.query.filter_by(source="report").first().account.slug == "hapitech"
    assert len(_outbox(app)) == n + 1
    assert "Mohammad Zaheer" in pub.get("/rv/rolands").get_data(as_text=True)                # still visible


def test_review_export_files_google_and_facebook(app):
    import io
    import json as _json
    from models import db
    from models.core import Account
    from models.reviews import Review
    with app.app_context():
        a = Account.query.filter_by(slug="rayg").first()
        db.session.add(Review(account_id=a.id, source="google", author_name="Paul Martin", rating=5, body="Old copy…",
                              status="published"))
        db.session.commit()
        before = Review.query.filter_by(account_id=a.id).count()
    g = {"format": "hapitech-reviews/1", "source": "google", "business": "RayG Handyman Service",
         "copied_at": "2026-11-24T10:00:00Z", "summary": {"rating": 4.8, "count": 63}, "reviews": [
        {"id": "ChZDSUhNMG", "author": "Paul Martin", "rating": 5, "date": "6 months ago",
         "text": "Ray has just put in a complete new bathroom for me, and it looks stunning. Full text here.",
         "photos": ["https://lh3.googleusercontent.com/x=w1600-h1600"], "price": None,
         "reply": {"date": "6 months ago", "text": "Thank you so much!"}},
        {"id": "ChZDSUhNMH", "author": "Donna Latham", "rating": 2, "date": "3 months ago", "text": "Do not use him",
         "photos": [], "price": "Overpriced", "reply": None}]}
    fb = {"format": "hapitech-reviews/1", "source": "facebook", "page": "rayghandymanservice", "business": "RayG Handyman services",
          "url": "https://www.facebook.com/RayGHandymanservice/reviews", "copied_at": "2026-11-24T10:00:00Z",
          "summary": {"recommend_pct": 98, "count": 71}, "reviews": [
        {"id": "https://www.facebook.com/garry/posts/pfbid123", "author": "Garry Twyford", "recommends": True,
         "header": "Garry Twyford recommends RayG Handyman services.", "time": "Monday 28 June 2021 at 14:54",
         "text": "Meet Ray a couple of weeks ago…", "photos": [],
         "replies": [{"label": "Comment by RayG Handyman services", "time": "Monday 28 June 2021 at 17:23",
                      "text": "RayG Handyman services\n·\n5y\nGarry Twyford thank you very much\nReply\n1"}]},
        {"id": "https://www.facebook.com/someone/posts/pfbid456", "author": "Someone Else", "recommends": False,
         "time": "2y", "text": "Not great", "photos": [], "replies": []}]}
    adm = app.test_client(); _login(adm, "admin@test")
    page = adm.get("/admin/reviews/import").get_data(as_text=True)
    assert "Google Maps script" in page and "data-review-id" in page and "recommends" in page
    for data in (g, fb, g):                        # google twice: nothing doubles
        r = adm.post("/admin/reviews/import", data={"csrf_token": _csrf(adm, "/admin/reviews/import"), "client": "rayg",
                     "file": (io.BytesIO(_json.dumps(data).encode()), "x.json")}, content_type="multipart/form-data")
        assert "Imported" in r.get_data(as_text=True)
    with app.app_context():
        a = Account.query.filter_by(slug="rayg").first()
        pm = Review.query.filter_by(account_id=a.id, author_name="Paul Martin").all()
        assert len(pm) == 1 and pm[0].external_id == "google:ChZDSUhNMG" and pm[0].body.endswith("Full text here.")
        assert pm[0].reply.body == "Thank you so much!" and pm[0].photo_count == 1
        assert Review.query.filter_by(author_name="Donna Latham").first().rating == 2
        garry = Review.query.filter_by(author_name="Garry Twyford").first()
        assert garry.source == "facebook" and garry.recommends and garry.rating == 5
        assert garry.reviewed_at.year == 2021 and garry.reply.body == "Garry Twyford thank you very much"
        assert Review.query.filter_by(author_name="Someone Else").first().recommends is False
        assert float(a.google_rating) == 4.8 and a.facebook_pct == 98 and a.facebook_count == 71
        assert Review.query.filter_by(account_id=a.id).count() == before + 3       # Paul updated, 3 new, none doubled
    pub = app.test_client().get("/rv/rayg").get_data(as_text=True)
    assert "98%" in pub and "4.8★" in pub and "👍 Recommends" in pub and "Doesn&#39;t recommend" in pub


def test_reply_skip_rate_shortcuts_platforms_extras(app):
    import datetime as dt
    import json as _json
    from models import db
    from models.core import Account
    from models.reviews import Review, ReviewReply
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.shortcuts = _json.dumps([["Bark", "https://www.bark.com/en/gb/login/"], ["Bad", "http://insecure"]])
        now = dt.datetime.utcnow()
        r1 = Review(account_id=a.id, source="google", author_name="Old One", rating=5, body="ok", status="published", reviewed_at=now)
        r2 = Review(account_id=a.id, source="google", author_name="Replied", rating=5, body="ok", status="published", reviewed_at=now)
        db.session.add_all([r1, r2]); db.session.flush()
        db.session.add(ReviewReply(review_id=r2.id, body="thanks"))
        db.session.commit(); rid = r1.id
    o = app.test_client(); _login(o, "roland@test")
    home = o.get("/portal/").get_data(as_text=True)
    assert "Reply rate" in home and "% this month" in home
    assert "Old One" in o.get("/portal/reviews?show=unreplied").get_data(as_text=True)
    _form(o, f"/portal/reviews/{rid}", {"action": "skip-reply"}, page="/portal/reviews")
    assert "Old One" not in o.get("/portal/reviews?show=unreplied").get_data(as_text=True)
    page = o.get("/portal/reviews").get_data(as_text=True)
    assert "Needs a reply after all" in page and "Get reviewed in more places" in page and "Trustpilot" in page
    jobs = o.get("/portal/jobs").get_data(as_text=True)
    assert "https://www.bark.com/en/gb/login/" in jobs and "http://insecure" not in jobs and "＋" in jobs
    _form(o, "/portal/requests/work", {"kind": "other", "what": "Checkatrade", "prefix": "Please add a Jobs shortcut to: ", "back": "jobs"}, page="/portal/jobs")
    plan = o.get("/portal/plan").get_data(as_text=True)
    assert "AI chat assistant" in plan and "I'm interested" in plan
    _form(o, "/portal/extras/ai_chat", {}, page="/portal/plan")
    with app.app_context():
        from models.work import Lead
        assert Account.query.filter_by(slug="rolands").first().addon("ai_chat").status == "requested"
        assert Lead.query.filter(Lead.message.like("Please add a Jobs shortcut to: Checkatrade")).count() == 1
    assert "Requested ✓" in o.get("/portal/plan").get_data(as_text=True)
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, "/admin/clients/rolands/extras/ai_chat", {"status": "active"}, page="/admin/clients/rolands")
    assert "On</span>" in o.get("/portal/plan").get_data(as_text=True)


def test_unedited_sections_follow_new_defaults_and_arent_sent(app):
    import json as _json
    from models import db
    from models.core import Account
    from models.content import ContentBlock
    from utils.content_blocks import ensure_blocks
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.domain = "rolandshandyman.co.uk"
        ensure_blocks(a, None); db.session.commit()
        pol = ContentBlock.query.filter_by(account_id=a.id, key="legal.privacy.page").first()
        assert "saved in Roland's business dashboard" in pol.data
        pol.default_value = pol.value = _json.dumps("an older policy")          # as if made before the update
        hero = ContentBlock.query.filter_by(account_id=a.id, key="hero.title").first()
        hero.value = _json.dumps("Edited by Roland")
        db.session.commit()
        ensure_blocks(a, None); db.session.commit()
        assert "saved in Roland's business dashboard" in ContentBlock.query.filter_by(account_id=a.id, key="legal.privacy.page").first().data
        assert ContentBlock.query.filter_by(account_id=a.id, key="hero.title").first().data == "Edited by Roland"
    content = app.test_client().get("/api/v1/sites/rolands/content", headers=_site_key(app, "rolands")).json["content"]
    assert content == {"hero.title": "Edited by Roland"}           # only real edits are sent


def test_review_search_filters(app):
    from models import db
    from models.core import Account
    from models.reviews import Review
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        db.session.add_all([Review(account_id=a.id, author_name="Zed Finder", rating=2, body="Wardrobe wobbles a bit", source="google", status="published"),
                            Review(account_id=a.id, author_name="Yan Other", rating=5, body="Lovely shelves", source="facebook", status="published")])
        db.session.commit()
    c = app.test_client(); _login(c, "roland@test")
    page = c.get("/portal/reviews?q=wardrobe").get_data(as_text=True)
    assert "Zed Finder" in page and "Yan Other" not in page and "1 review matches" in page
    page = c.get("/portal/reviews?src=facebook&stars=5").get_data(as_text=True)
    assert "Yan Other" in page and "Zed Finder" not in page
    a = app.test_client(); _login(a, "admin@test")
    page = a.get("/admin/reviews?status=all&q=zed").get_data(as_text=True)
    assert "Zed Finder" in page and "Yan Other" not in page and 'data-open-dlg="rvSettings"' in page and "Remove from public view" in page
    import re as _re
    assert "dialog" not in _re.search(r"<title>(.*?)</title>", page, _re.S).group(1)            # pop-up in the page, not the title
    assert page.index('id="rvSettings"') > page.index("</head>")
    assert 'class="btn btn--danger btn--sm" name="action" value="remove"' not in page     # no big red button any more
    j = app.test_client(); _login(j, "roland@test")
    jobs = j.get("/portal/jobs").get_data(as_text=True)
    assert 'data-open-dlg="shortcutDialog"' in jobs
    rv = j.get("/portal/reviews").get_data(as_text=True)
    assert "Trustpilot" in rv and "Bark" not in rv and "Somewhere else?" in rv and "small monthly cost" in rv


def test_google_new_badge_is_not_part_of_review():
    from utils.review_import import google_text
    item = {"date": "2 weeks ago", "text": "", "raw": "Lamia\n2 weeks ago\nNEW\nRolands did an amazing job\nLike\nShare"}
    out = google_text(item)
    assert (out[0] if isinstance(out, tuple) else out).startswith("Rolands did an amazing job")


def test_generic_invite_reviews_only_and_mail_copy(app):
    import email
    import glob
    import os
    from models import db
    from models.core import Account, SystemState
    a = app.test_client(); _login(a, "admin@test")
    page = a.get("/admin/updates?show=invite").get_data(as_text=True)
    assert "Done inviting Ray and Roland?" in page and "Preview for:" in page
    _form(a, "/admin/updates", {"kind": "invite-mode", "mode": "generic"}, page="/admin/updates?show=invite")
    page = a.get("/admin/updates?show=invite").get_data(as_text=True)
    assert "Invite someone to a dashboard" in page
    _form(a, "/admin/updates/generic", {"business": "Shine Cleaners", "contact_name": "Sam Shine", "email": "sam@shine.test",
                                        "features": "reviews"}, page="/admin/updates?show=invite")
    page = a.get("/admin/updates?show=invite").get_data(as_text=True)
    assert "Shine Cleaners" in page and "HapiTech Reviews dashboard is ready" in page
    with app.app_context():
        acc = Account.query.filter_by(name="Shine Cleaners").first()
        assert acc.feature_set == {"reviews"}
        slug = acc.slug
    out = os.path.join(app.instance_path, "mail_outbox")
    before = set(glob.glob(out + "/*.eml"))
    _form(a, "/admin/updates", {"kind": "generic", "client": slug, "action": "send", "back": "invite"}, page="/admin/updates?show=invite")
    new = set(glob.glob(out + "/*.eml")) - before
    assert len(new) == 1
    msg = email.message_from_string(open(new.pop()).read())
    assert msg["To"] == "sam@shine.test" and msg["Bcc"] == "aaron+sent@hapitech.dev"
    s = app.test_client(); _login(s, "sam@shine.test")
    home = s.get("/portal/").get_data(as_text=True)
    assert "/portal/reviews" in home and "/portal/jobs" not in home and "Edit my website" not in home
    r = s.get("/portal/jobs")
    assert r.status_code == 302
    with app.app_context():
        db.session.delete(db.session.get(SystemState, "invite_mode")); db.session.commit()


def test_last_seen_and_share_tip_pref(app):
    from models.core import User
    c = app.test_client(); _login(c, "roland@test")
    c.get("/portal/")
    with app.app_context():
        u = User.query.filter_by(email="roland@test").first()
        assert u.last_seen_at is not None and not u.pref("share_tip_off")
    page = c.get("/portal/settings").get_data(as_text=True)
    assert "Sharing posts" in page
    _form(c, "/portal/settings", {"action": "prefs"}, page="/portal/settings")          # box unticked
    with app.app_context():
        assert User.query.filter_by(email="roland@test").first().pref("share_tip_off") is True
    a = app.test_client(); _login(a, "admin@test")
    assert "Last seen" in a.get("/admin/clients").get_data(as_text=True)


def test_review_link_expires_and_can_be_renewed(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.reviews import ReviewRequest
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        r = ReviewRequest(account_id=a.id, customer_name="Old Olly", created_at=dt.datetime.utcnow() - dt.timedelta(days=31))
        db.session.add(r); db.session.commit()
        rid, token = r.id, r.token
        assert r.state == "expired"
    pub = app.test_client().get(f"/r/{token}")
    assert pub.status_code == 410 and "expired" in pub.get_data(as_text=True)
    o = app.test_client(); _login(o, "roland@test")
    assert o.get("/portal/requests").headers["Location"].endswith("/portal/reviews?show=sent")
    page = o.get("/portal/reviews?show=sent").get_data(as_text=True)
    assert "Link expired" in page and "Send a fresh link" in page and 'aria-current="page">Sent<' in page
    _form(o, f"/portal/ask/{rid}", {"action": "renew"}, page="/portal/reviews?show=sent")
    with app.app_context():
        r = db.session.get(ReviewRequest, rid)
        assert r.state == "sent" and r.token != token and r.days_left >= 29
    assert app.test_client().get(f"/r/{token}").status_code == 404               # old link gone
    adm = app.test_client(); _login(adm, "admin@test")
    page = adm.get("/admin/clients/rolands?tab=reviews").get_data(as_text=True)
    assert "Review requests sent" in page and "Old Olly" in page



def test_own_sites_count_visits_and_take_edits(app):
    import json as _json
    from models import db
    from models.content import ContentBlock, SiteVisit
    from models.core import Account
    from utils.content_blocks import ensure_blocks
    from utils.hapitech_account import ensure_own_sites, get
    with app.app_context():
        ensure_own_sites()
        h = get()
        assert ensure_blocks(h, None) > 50
        b = ContentBlock.query.filter_by(account_id=h.id, key="hero.heading1").first()
        b.value = _json.dumps("Tech that just works")
        db.session.commit()
    c = app.test_client()
    home = c.get("/", headers={"User-Agent": "Mozilla/5.0 (iPhone)", "Referer": "https://www.google.com/"}).get_data(as_text=True)
    assert "Tech that just works" in home and '<span class="acc">small' not in home
    assert "What we can help with." in home                       # unedited text unchanged
    c.get("/rv/", headers={"User-Agent": "Mozilla/5.0"})
    c.get("/", headers={"User-Agent": "Googlebot/2.1"})            # bots aren't counted
    with app.app_context():
        h = Account.query.filter_by(slug="hapitech").first()
        r = Account.query.filter_by(slug="hapitech-reviews").first()
        assert sum(v.count for v in SiteVisit.query.filter_by(account_id=h.id).all()) == 1
        assert SiteVisit.query.filter_by(account_id=h.id).first().ref == "google"
        assert SiteVisit.query.filter_by(account_id=r.id, path="/").first().count == 1



def test_remove_review_request_kills_link(app):
    from models import db
    from models.core import Account
    from models.reviews import ReviewRequest
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        r1, r2 = ReviewRequest(account_id=a.id, customer_name="Cancel Me"), ReviewRequest(account_id=a.id, customer_name="Admin Cancels")
        db.session.add_all([r1, r2]); db.session.commit()
        (id1, t1), (id2, t2) = (r1.id, r1.token), (r2.id, r2.token)
    assert app.test_client().get(f"/r/{t1}").status_code == 200
    o = app.test_client(); _login(o, "roland@test")
    assert "Remove this request?" in o.get("/portal/reviews?show=sent").get_data(as_text=True)
    _form(o, f"/portal/ask/{id1}", {"action": "remove"}, page="/portal/reviews?show=sent")
    assert app.test_client().get(f"/r/{t1}").status_code == 404
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, f"/admin/clients/rolands/requests/{id2}/remove", {}, page="/admin/clients/rolands?tab=reviews")
    assert app.test_client().get(f"/r/{t2}").status_code == 404
    with app.app_context():
        assert db.session.get(ReviewRequest, id1) is None and db.session.get(ReviewRequest, id2) is None


# ---------------------------------------------------------------- new-review emails, HapiTech on hapitech.report, photo viewer

def _leave_via_link(app, slug, name, photo=True):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.reviews import ReviewRequest
    with app.app_context():
        a = Account.query.filter_by(slug=slug).first()
        rq = ReviewRequest(account_id=a.id, customer_name=name, created_at=dt.datetime.utcnow())
        db.session.add(rq)
        db.session.commit()
        token = rq.token
    cust = app.test_client()
    tok = re.search(r'name="csrf-token" content="([^"]+)"', cust.get(f"/r/{token}").get_data(as_text=True)).group(1)
    data = {"csrf_token": tok, "rating": "5", "name": name, "body": "Lovely job, thank you very much"}
    if photo:
        data["photos"] = (_png(), "pic.png")
    r = cust.post(f"/r/{token}", data=data, content_type="multipart/form-data")
    assert r.status_code == 200


def test_new_review_emails_owner_and_admin(app):
    from models import db
    from models.core import Account
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().contact_email = "roland@test"
        db.session.commit()
    _leave_via_link(app, "rolands", "Sarah")
    mails = _outbox(app)
    to_owner = [m for m in mails if "roland@test" in m and "New 5-star review from Sarah" in m]
    to_admin = [m for m in mails if "aaron@hapitech.dev" in m and "New review for Roland's Handyman" in m]
    assert to_owner and "Reply to it" in to_owner[0] and "1 photo" in to_owner[0]
    assert to_admin and ("as=rolands" in to_admin[0] or "as=3Drolands" in to_admin[0])


def test_hapitech_own_review_emails_admin_once_and_is_listed_on_report(app):
    from utils.hapitech_account import ensure_own_sites
    with app.app_context():
        ensure_own_sites()
    before = len(_outbox(app))
    _leave_via_link(app, "hapitech", "Rolands")
    new = _outbox(app)[before:]
    assert len(new) == 1 and "aaron@hapitech.dev" in new[0]          # contact is Aaron: one email, not two
    pub = app.test_client()
    home = pub.get("/", base_url="https://hapitech.report").get_data(as_text=True)
    assert 'href="/hapitech"' in home
    assert "/hapitech-reviews" not in home                            # our other own sites stay off the list
    page = pub.get("/hapitech", base_url="https://hapitech.report").get_data(as_text=True)
    assert 'data-lightbox="r' in page and 'target="_blank" rel="noopener"><img' not in page
    site = pub.get("/").get_data(as_text=True)                        # hapitech.dev home shows the photo too
    assert 'class="rev__pics"' in site and "js/lightbox.js" in site


# ---------------------------------------------------------------- admin Tasks

def test_tasks_create_note_remind_and_privacy(app):
    import datetime as dt
    from models.tasks import Task
    adm = app.test_client(); _login(adm, "admin@test")
    r = _form(adm, "/admin/tasks/new", {"title": "Ask Roland for Google access", "for": "rolands", "status": "waiting",
                                         "remind_on": "", "note": "Do it after he logs in.", "author": "claude"},
              page="/admin/tasks/new")
    assert r.status_code == 302
    with app.app_context():
        t = Task.query.one()
        tid, assert_tag = t.id, t.tag
        assert assert_tag == "Roland's Handyman" and t.status == "waiting" and t.notes[0].author_kind == "claude"
    _form(adm, f"/admin/tasks/{tid}", {"action": "note", "note": "He said yes", "author": "client"}, page=f"/admin/tasks/{tid}")
    _form(adm, f"/admin/tasks/{tid}", {"action": "snooze", "by": "1w"}, page=f"/admin/tasks/{tid}")
    page = adm.get(f"/admin/tasks/{tid}").get_data(as_text=True)
    assert "He said yes" in page and "Claude" in page and "Client" in page
    with app.app_context():
        assert Task.query.get(tid).remind_on == dt.date.today() + dt.timedelta(days=7)
    infra = _form(adm, "/admin/tasks/new", {"title": "Renew SSL", "for": "infra"}, page="/admin/tasks/new")
    assert infra.status_code == 302
    assert "HapiTech infra" in adm.get("/admin/tasks?for=infra").get_data(as_text=True)
    assert "Ask Roland" in adm.get("/admin/clients/rolands").get_data(as_text=True)          # on the client page
    home = adm.get("/admin/").get_data(as_text=True)
    assert "Renew SSL" in home and "Ask Roland" not in home       # overview: to-dos; waiting ones only once due
    owner = app.test_client(); _login(owner, "roland@test")
    assert owner.get("/admin/tasks").status_code == 403                                     # clients never see tasks


def test_task_reminder_email_and_badge(app):
    import datetime as dt
    from models import db
    from models.tasks import Task, TaskNote
    from utils.tasks import send_task_reminders
    with app.app_context():
        t = Task(title="Follow up: has Roland logged in?", remind_on=dt.date.today())
        t.notes.append(TaskNote(author_kind="claude", body="Check users.last_login_at"))
        db.session.add(t); db.session.commit()
    adm = app.test_client(); _login(adm, "admin@test")
    assert re.search(r'Tasks</span>\s*<em class="side__badge">1<', adm.get("/admin/").get_data(as_text=True)) or \
        "side__badge" in adm.get("/admin/tasks").get_data(as_text=True)
    with app.test_request_context("/", base_url="https://hapitech.test"):
        assert send_task_reminders() == 1
        assert send_task_reminders() == 0                                                   # once per date
    assert any("Follow up: has Roland logged in?" in m and "Reminder T-" in m for m in _outbox(app))


def test_change_request_accepted_becomes_task_and_closes_when_done(app):
    from models import db
    from models.core import Account, ChangeRequest
    from models.tasks import Task
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        cr = ChangeRequest(account_id=a.id, body="Please change my phone number\nto the new one")
        db.session.add(cr); db.session.commit()
        crid = cr.id
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, f"/admin/requests/{crid}", {"status": "doing"}, page="/admin/requests")
    _form(adm, f"/admin/requests/{crid}", {"status": "doing"}, page="/admin/requests")      # no duplicate task
    with app.app_context():
        ts = Task.query.filter_by(change_request_id=crid).all()
        assert len(ts) == 1 and ts[0].title == "Change: Please change my phone number"
        assert ts[0].notes[0].author_kind == "client" and "new one" in ts[0].notes[0].body
        tid = ts[0].id
    assert f"/admin/tasks/{tid}" in adm.get("/admin/requests").get_data(as_text=True)
    _form(adm, f"/admin/tasks/{tid}", {"action": "status", "status": "done"}, page=f"/admin/tasks/{tid}")
    with app.app_context():
        assert db.session.get(ChangeRequest, crid).status == "done"


def test_client_sees_only_shared_tasks_and_notes_and_can_comment(app):
    from models import db
    from models.core import Account
    from models.tasks import Task, TaskNote
    with app.app_context():
        ro, ray = Account.query.filter_by(slug="rolands").first(), Account.query.filter_by(slug="rayg").first()
        ro.contact_email = "roland@test"
        shared = Task(title="New kitchen page", account_id=ro.id, shared=True)
        shared.notes.append(TaskNote(author_kind="aaron", body="Draft is ready", shared=True))
        shared.notes.append(TaskNote(author_kind="claude", body="SECRET internal steps", shared=False))
        private = Task(title="Chase Roland for Google access", account_id=ro.id, shared=False)
        other = Task(title="Ray's thing", account_id=ray.id, shared=True)
        db.session.add_all([shared, private, other]); db.session.commit()
        sid, pid, oid = shared.id, private.id, other.id
    c = app.test_client(); _login(c, "roland@test")
    lst = c.get("/portal/changes").get_data(as_text=True)
    assert f"T-{sid}" in lst and "New kitchen page" in lst and "Chase Roland" not in lst and "Ray's thing" not in lst
    page = c.get(f"/portal/changes/T-{sid}").get_data(as_text=True)
    assert "Draft is ready" in page and "SECRET" not in page
    assert c.get(f"/portal/changes/T-{pid}").status_code == 404 and c.get(f"/portal/changes/T-{oid}").status_code == 404
    assert c.get(f"/admin/tasks/{sid}").status_code == 403                       # can't edit or delete
    assert c.post(f"/admin/tasks/{sid}", data={"action": "delete"}).status_code in (400, 403)
    # search by ID and by words (only what they can see)
    assert c.get(f"/portal/changes?q=T-{sid}").headers["Location"].endswith(f"/portal/changes/T-{sid}")
    assert "New kitchen page" not in c.get("/portal/changes?q=SECRET").get_data(as_text=True)
    # comment -> Aaron emailed with a direct admin link
    _form(c, f"/portal/changes/T-{sid}", {"body": "Looks great, go ahead"}, page=f"/portal/changes/T-{sid}")
    with app.app_context():
        n = Task.query.get(sid).notes[-1]
        assert n.author_kind == "client" and n.shared and n.body == "Looks great, go ahead"
    mail = [m for m in _outbox(app) if f"replied on T-{sid}" in m]
    assert mail and (f"/admin/tasks/{sid}" in mail[0])
    # Aaron replies (shared) -> client emailed with a direct dashboard link
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, f"/admin/tasks/{sid}", {"action": "note", "note": "Live now", "author": "aaron", "note_shared": "1"},
          page=f"/admin/tasks/{sid}")
    to_client = [m for m in _outbox(app) if "To: roland@test" in m and f"T-{sid}" in m and "Aaron replied" in m]
    assert to_client and f"/portal/changes/T-{sid}" in to_client[-1].replace("=\n", "")
    assert "Live now" in c.get(f"/portal/changes/T-{sid}").get_data(as_text=True)
    # a private note never reaches the client
    _form(adm, f"/admin/tasks/{sid}", {"action": "note", "note": "PRIVATE thought", "author": "aaron"}, page=f"/admin/tasks/{sid}")
    assert "PRIVATE thought" not in c.get(f"/portal/changes/T-{sid}").get_data(as_text=True)
    # admin search
    assert adm.get(f"/admin/tasks?q=T-{sid}").headers["Location"].endswith(f"/admin/tasks/{sid}")
    assert "Chase Roland" in adm.get("/admin/tasks?q=google").get_data(as_text=True)


def test_change_request_flow_emails_client_and_admin_with_links(app):
    from models import db
    from models.core import Account, ChangeRequest
    from models.tasks import Task
    with app.app_context():
        Account.query.filter_by(slug="rolands").first().contact_email = "roland@test"; db.session.commit()
    c = app.test_client(); _login(c, "roland@test")
    r = _form(c, "/portal/changes", {"body": "Add a gutter cleaning page"}, page="/portal/changes")
    with app.app_context():
        cr = ChangeRequest.query.filter_by(body="Add a gutter cleaning page").one(); crid = cr.id
    assert r.headers["Location"].endswith(f"/portal/changes/R-{crid}")
    assert "Waiting for Aaron" in c.get(f"/portal/changes/R-{crid}").get_data(as_text=True)
    to_admin = [m for m in _outbox(app) if f"Change request R-{crid}" in m]
    assert to_admin and f"r={crid}" in to_admin[0].replace("=3D", "=").replace("=\n", "")
    adm = app.test_client(); _login(adm, "admin@test")
    _form(adm, f"/admin/requests/{crid}", {"status": "doing"}, page="/admin/requests")
    with app.app_context():
        t = Task.query.filter_by(change_request_id=crid).one(); tid = t.id
        assert t.shared and t.notes[0].shared
    accepted = [m for m in _outbox(app) if "To: roland@test" in m and "Accepted" in m]
    assert accepted and f"/portal/changes/T-{tid}" in accepted[-1].replace("=\n", "")
    assert c.get(f"/portal/changes/R-{crid}").headers["Location"].endswith(f"/portal/changes/T-{tid}")
    assert "Gutter" in adm.get("/admin/clients/rolands?tab=requests").get_data(as_text=True).replace("gutter", "Gutter")
    assert f"T-{tid}" in adm.get("/admin/clients/rolands?tab=tasks").get_data(as_text=True)
    _form(adm, f"/admin/requests/{crid}", {"status": "done"}, page="/admin/requests")
    with app.app_context():
        assert Task.query.get(tid).status == "done"
    assert any("To: roland@test" in m and f"Done (T-{tid})" in m for m in _outbox(app))


def test_hapitech_job_accepted_becomes_client_task(app):
    from models import db
    from models.core import Account
    from models.tasks import Task
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        ht = hapitech()
        ro = Account.query.filter_by(slug="rolands").first()
        lead = Lead(account_id=ht.id, source="request", for_account_id=ro.id, name=ro.name, email="roland@test",
                    title="Website change: new gallery", message="Please add a gallery page")
        db.session.add(lead); db.session.commit(); lid = lead.id
    adm = app.test_client(); _login(adm, "admin@test")
    page = adm.get(f"/portal/jobs/{lid}?as=hapitech").get_data(as_text=True)
    assert "Accept: task for Roland" in page and "Book it in" not in page
    r = _form(adm, f"/portal/jobs/{lid}?as=hapitech", {"action": "accept-task"}, page=f"/portal/jobs/{lid}?as=hapitech")
    with app.app_context():
        t = Task.query.filter_by(lead_id=lid).one()
        assert t.account.slug == "rolands" and t.shared and db.session.get(Lead, lid).status == "accepted"
        assert t.notes[0].body == "Please add a gallery page"
        tid = t.id
    assert r.headers["Location"].endswith(f"/admin/tasks/{tid}")
    assert f"T-{tid}" in adm.get(f"/portal/jobs/{lid}?as=hapitech").get_data(as_text=True)
    owner = app.test_client(); _login(owner, "roland@test")
    assert "new gallery" in owner.get("/portal/changes").get_data(as_text=True)


def test_change_requests_hide_completed_and_due_tasks_highlighted(app):
    import datetime as dt
    from models import db
    from models.core import Account, ChangeRequest
    from models.tasks import Task
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        db.session.add_all([ChangeRequest(account_id=a.id, body="Open one please"),
                            ChangeRequest(account_id=a.id, body="Finished thing", status="done"),
                            Task(title="Due thing", remind_on=dt.date.today())])
        db.session.commit()
    adm = app.test_client(); _login(adm, "admin@test")
    page = adm.get("/admin/requests").get_data(as_text=True)
    assert "Open one please" in page and "Finished thing" not in page
    assert "Finished thing" in adm.get("/admin/requests?show=done").get_data(as_text=True)
    tab = adm.get("/admin/clients/rolands?tab=requests").get_data(as_text=True)
    assert "Open one please" in tab and "Finished thing" not in tab
    lst = adm.get("/admin/tasks").get_data(as_text=True)
    assert "task-row is-due" in lst and "1 reminder due" in lst


def test_jobs_today_email_upcoming_on_home_and_review_link(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    from utils.tasks import send_jobs_today
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.contact_email = "roland@test"
        today9 = dt.datetime.combine(dt.date.today(), dt.time(9))
        l = Lead(account_id=a.id, name="Sarah Jones", status="booked", start_at=today9, days=1, title="Fit shelves",
                 postcode="WV1 1AA")
        n = Lead(account_id=a.id, name="Tom", status="accepted", title="Hang doors")
        db.session.add_all([l, n]); db.session.commit(); lid = l.id
    with app.test_request_context("/", base_url="https://hapitech.test"):
        assert send_jobs_today(dt.datetime.combine(dt.date.today(), dt.time(7, 5))) == 1
        assert send_jobs_today(dt.datetime.combine(dt.date.today(), dt.time(9))) == 0          # once a day
    mail = [m for m in _outbox(app) if "To: roland@test" in m and "Today: Sarah Jones at 09:00" in m]
    assert mail and f"/portal/jobs/{lid}" in mail[0].replace("=\n", "")
    c = app.test_client(); _login(c, "roland@test")
    home = c.get("/portal/").get_data(as_text=True)
    assert "Your work" in home and f"/portal/jobs/{lid}" in home and "Needs a date" in home
    job = c.get(f"/portal/jobs/{lid}").get_data(as_text=True)
    assert "Show the review QR code" in job and "name=Sarah" in job
    ask = c.get("/portal/ask?name=Sarah&job=Fit+shelves").get_data(as_text=True)
    assert 'value="Sarah"' in ask and 'value="Fit shelves"' in ask


def test_hapitech_homepage_request_loop_and_calendar_reminders(app):
    import datetime as dt
    from models import db
    from models.core import User
    from models.tasks import Task
    from models.work import Lead
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        ht = hapitech()
        ht.calendar_token = "x" * 24
        db.session.add(User(email="owner@hapitech.test", username="owner@hapitech.test", role="owner", account_id=ht.id,
                            name="Aaron (as a client)"))
        lead = Lead(account_id=ht.id, source="enquiry", name="Aaron", email="owner@hapitech.test",
                    title="Website build", message="Testing the loop")
        db.session.add(lead); db.session.commit(); lid = lead.id
    adm = app.test_client(); _login(adm, "admin@test")
    assert "Accept: task for HapiTech" in adm.get(f"/portal/jobs/{lid}?as=hapitech").get_data(as_text=True)
    _form(adm, f"/portal/jobs/{lid}?as=hapitech", {"action": "accept-task"}, page=f"/portal/jobs/{lid}?as=hapitech")
    with app.app_context():
        t = Task.query.filter_by(lead_id=lid).one()
        assert t.account.slug == "hapitech" and t.shared
        t.remind_on = dt.date.today(); db.session.commit(); tid = t.id
    assert any("To: owner@hapitech.test" in m and f"Accepted (T-{tid})" in m for m in _outbox(app))   # the owner login hears
    assert not any("To: aaron@hapitech.dev" in m and f"Accepted (T-{tid})" in m for m in _outbox(app))
    owner = app.test_client(); _login(owner, "owner@hapitech.test")
    assert "Testing the loop" in owner.get(f"/portal/changes/T-{tid}").get_data(as_text=True)
    ics = app.test_client().get("/cal/" + "x" * 24 + ".ics").get_data(as_text=True)
    assert f"T-{tid}" in ics and "VALARM" in ics
    cal = adm.get("/portal/calendar?as=hapitech").get_data(as_text=True)
    assert f"T-{tid}" in cal


def _html_of(raw):
    import email as _email
    m = _email.message_from_string(raw)
    for part in m.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode()
    return ""


def test_emails_have_no_images_show_content_and_use_client_branding(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        a.contact_email, a.brand_colour, a.logo_path = "roland@test", "#f97316", "media/clients/x.png"
        db.session.commit()
    # homepage enquiry: saved, emailed with the full message and a link straight to the job
    pub = app.test_client()
    tok = _csrf(pub)
    r = pub.post("/contact", json={"name": "Jo", "email": "jo@example.com", "message": "Line one\nLine two",
                                   "need": "Website"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200
    with app.app_context():
        lid = Lead.query.filter_by(email="jo@example.com").one().id
    raw = [m for m in _outbox(app) if "jo@example.com" in m and "Contact" in m][-1]
    html = _html_of(raw)
    assert "Line one\nLine two" in html and f"/portal/jobs/{lid}" in html and "Open it in Jobs" in html
    # a client's own notification: their colour, no HapiTech footer, no images anywhere
    c = app.test_client(); _login(c, "roland@test")
    _form(c, "/portal/changes", {"body": "Please add\na gutters page"}, page="/portal/changes")
    adm = app.test_client(); _login(adm, "admin@test")
    from models.core import ChangeRequest
    with app.app_context():
        crid = ChangeRequest.query.one().id
    _form(adm, f"/admin/requests/{crid}", {"status": "doing"}, page="/admin/requests")
    accepted = _html_of([m for m in _outbox(app) if "To: roland@test" in m and "Accepted" in m][-1])
    assert "Please add\na gutters page" in accepted and "What you asked" in accepted
    with app.test_request_context("/", base_url="https://hapitech.test"):
        from utils import email_html
        _, own = email_html.build("x", account=Account.query.filter_by(slug="rolands").first(), heading="Hi", lines=["a"])
        _, ht = email_html.build("x", heading="Hi", lines=["a"])
    assert "#f97316" in own and "Sent by" not in own and "Roland's Handyman" in own.replace("&#39;", "'")
    assert "Sent by" in ht
    assert all("<img" not in _html_of(m) for m in _outbox(app))


def test_task_quote_receipt_and_job_sync(app):
    from models import db
    from models.core import Account
    from models.tasks import Task
    from models.work import Invoice, Lead
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        hapitech()
        ro = Account.query.filter_by(slug="rolands").first()
        ro.contact_email, ro.contact_name = "roland@test", "Roland"
        t = Task(title="New gallery page", account_id=ro.id, shared=True)
        db.session.add(t); db.session.commit(); tid, roid = t.id, ro.id
    adm = app.test_client(); _login(adm, "admin@test")
    r = _form(adm, f"/admin/tasks/{tid}", {"action": "quote"}, page=f"/admin/tasks/{tid}")
    with app.app_context():
        t = db.session.get(Task, tid); lid = t.lead_id
        assert lid and t.lead.for_account_id == roid and t.lead.email == "roland@test"
    assert f"/portal/jobs/{lid}/quote" in r.headers["Location"]
    page = f"/portal/jobs/{lid}/quote?as=hapitech"
    r = _form(adm, page, {"desc": "Gallery page", "qty": "1", "price": "120", "vat_rate": "0", "action": "save"}, page=page)
    assert r.headers["Location"].endswith(f"/admin/tasks/{tid}#money")
    assert "£120" in adm.get(f"/admin/tasks/{tid}").get_data(as_text=True)
    # done -> straight to the invoice; sent = Invoiced; Mark paid = Paid; then a receipt
    r = _form(adm, f"/admin/tasks/{tid}", {"action": "status", "status": "done"}, page=f"/admin/tasks/{tid}")
    assert f"/portal/jobs/{lid}/invoice" in r.headers["Location"]
    inv_page = f"/portal/jobs/{lid}/invoice?as=hapitech"
    _form(adm, inv_page, {"desc": "Gallery page", "qty": "1", "price": "120", "vat_rate": "0", "action": "send"}, page=inv_page)
    with app.app_context():
        assert db.session.get(Task, tid).stage == "invoiced"
    sent = _html_of([m for m in _outbox(app) if "To: roland@test" in m and "Invoice INV" in m][-1])
    assert f"T-{tid}" in sent and "Thanks! Use the payment link provided" in sent        # task ref + default message
    _form(adm, f"/admin/tasks/{tid}", {"action": "paid"}, page=f"/admin/tasks/{tid}")
    with app.app_context():
        assert db.session.get(Task, tid).stage == "paid"
    _form(adm, f"/admin/tasks/{tid}", {"action": "receipt"}, page=f"/admin/tasks/{tid}")
    with app.app_context():
        assert db.session.get(Lead, lid).status == "done"
        inv = Invoice.query.filter_by(lead_id=lid).one()
        assert inv.status == "paid" and inv.totals[2] == 120 and inv.sent_at
        token = inv.token
    mail = [m for m in _outbox(app) if "To: roland@test" in m and "Receipt INV" in m]
    assert mail and f"/i/{token}" in mail[-1].replace("=\n", "")
    assert "Receipt" in app.test_client().get(f"/i/{token}").get_data(as_text=True)


def test_quote_on_hapitech_job_makes_task_and_done_leaves_upcoming(app):
    from models import db
    from models.core import User
    from models.tasks import Task
    from models.work import Lead, Quote
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        ht = hapitech()
        db.session.add(User(email="owner@hapitech.test", username="owner@hapitech.test", role="owner", account_id=ht.id))
        lead = Lead(account_id=ht.id, source="enquiry", name="Aaron", email="owner@hapitech.test", title="IT support")
        db.session.add(lead); db.session.commit(); lid = lead.id
    adm = app.test_client(); _login(adm, "admin@test")
    page = f"/portal/jobs/{lid}/quote?as=hapitech"
    _form(adm, page, {"desc": "Setup", "qty": "1", "price": "50", "vat_rate": "0", "action": "save"}, page=page)
    with app.app_context():
        t = Task.query.filter_by(lead_id=lid).one()
        assert t.status == "waiting" and t.account.slug == "hapitech"
        token = Quote.query.filter_by(lead_id=lid).one().token
        q = Quote.query.filter_by(lead_id=lid).one(); q.status = "sent"; db.session.commit()
    cust = app.test_client()
    tok = re.search(r'name="csrf-token" content="([^"]+)"', cust.get(f"/q/{token}").get_data(as_text=True)).group(1)
    cust.post(f"/q/{token}", data={"csrf_token": tok, "answer": "accept"})
    with app.app_context():
        t = Task.query.filter_by(lead_id=lid).one(); tid = t.id
        assert t.status == "todo" and db.session.get(Lead, lid).status == "accepted"
    home = adm.get("/portal/?as=hapitech").get_data(as_text=True)
    assert "Needs a date" not in home                                     # it's a task, not a booking
    _form(adm, f"/admin/tasks/{tid}", {"action": "status", "status": "done"}, page=f"/admin/tasks/{tid}")
    with app.app_context():
        assert db.session.get(Lead, lid).status == "done"


def test_contact_email_details_in_box_message_alone(app):
    pub = app.test_client()
    tok = _csrf(pub)
    msg = "Looking for: IT support\nBusiness: Test Ltd\nPhone: 07700 900123\n\nPlease call me about my printer"
    pub.post("/contact", json={"name": "Jo", "email": "jo@example.com", "message": msg, "need": "IT support",
                               "business": "Test Ltd", "phone": "07700 900123"}, headers={"X-CSRF-Token": tok})
    html = _html_of([m for m in _outbox(app) if "jo@example.com" in m and "Contact" in m][-1])
    quote = html.split("Their message")[1].split("</div>")[0]
    assert "Please call me about my printer" in quote and "Looking for" not in quote
    assert ">Looking for<" in html and ">Test Ltd<" in html and ">07700 900123<" in html
    assert 'width="100%"' in html.split("Open it in Jobs")[0][-900:]


def test_client_home_shows_all_open_work_alerts_and_booked_links_to_calendar(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        b = Lead(account_id=a.id, name="Bea", status="booked", title="Shelves",
                 start_at=dt.datetime.combine(dt.date.today() + dt.timedelta(days=2), dt.time(10)), days=1)
        db.session.add_all([Lead(account_id=a.id, name="Rik", status="new", title="Light switch", source="website"),
                            Lead(account_id=a.id, name="Quinn", status="quoted", title="Decking"), b])
        db.session.commit(); bid = b.id
    c = app.test_client(); _login(c, "roland@test")
    home = c.get("/portal/").get_data(as_text=True)
    assert "Your work" in home and "Rik" in home and "New enquiries" in home and "Quinn" in home and "Bea" in home
    assert "has-alert" in home and "alert-dot" in home                       # Jobs icon + menu button flagged
    booked = c.get("/portal/jobs?show=booked").get_data(as_text=True)
    assert f"/portal/calendar#job-{bid}" in booked
    assert f'id="job-{bid}"' in c.get("/portal/calendar").get_data(as_text=True)


def test_dashboard_layout_switch_and_fitted_home(app):
    c = app.test_client(); _login(c, "roland@test")
    home = c.get("/portal/").get_data(as_text=True)
    assert 'class="site app app--portal page-home"' in home and "tipbar" in home
    assert 'localStorage.getItem("layout")' in home and "data-layout" in home       # phone-style unless "wide"
    settings = c.get("/portal/settings").get_data(as_text=True)
    assert 'data-look="layout" data-val="compact"' in settings and 'data-val="wide"' in settings
    adm = app.test_client(); _login(adm, "admin@test")
    ah = adm.get("/admin/").get_data(as_text=True)
    assert 'localStorage.getItem("layout")' in ah and 'class="tabbar' in ah and "data-layout-toggle" in ah   # admin matches


def test_pay_link_on_invoices_and_your_business_on_admin(app):
    from models import db
    from models.core import Account, Payment
    from models.work import Invoice, Lead
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        ht = hapitech()
        ro = Account.query.filter_by(slug="rolands").first()
        lead = Lead(account_id=ht.id, source="enquiry", status="new", name="Roland", email="roland@test",
                    for_account_id=ro.id, title="New page")
        db.session.add(lead); db.session.commit(); lid, roid = lead.id, ro.id
    adm = app.test_client(); _login(adm, "admin@test")
    # pick one provider in Settings; a bad link is refused
    s = "/portal/settings?as=hapitech"
    _form(adm, s, {"action": "business", "pay_link_on": "1", "pay_link_kind": "revolut", "pay_link": "https://evil.example/x"}, page=s)
    with app.app_context():
        assert hapitech().pay_link is None
    _form(adm, s, {"action": "business", "pay_link_on": "1", "pay_link_kind": "revolut", "pay_link": "revolut.me/aaron"}, page=s)
    with app.app_context():
        assert hapitech().pay_link_kind == "revolut" and hapitech().pay_link == "https://revolut.me/aaron"
    home = adm.get("/admin/").get_data(as_text=True)
    assert "Your business" in home and "New enquiry" in home
    # invoice sent: email + page have the Pay button; paid: recorded on the client's Money tab once
    page = f"/portal/jobs/{lid}/invoice?as=hapitech"
    _form(adm, page, {"desc": "Page", "qty": "1", "price": "80", "vat_rate": "0", "action": "send"}, page=page)
    mail = _html_of([m for m in _outbox(app) if "To: roland@test" in m and "Invoice INV" in m][-1])
    assert "Pay £80.00 with Revolut" in mail and "https://revolut.me/aaron" in mail
    with app.app_context():
        inv = Invoice.query.filter_by(lead_id=lid).one(); token, iid = inv.token, inv.id
    assert "Pay £80.00 with Revolut" in app.test_client().get(f"/i/{token}").get_data(as_text=True)
    assert "Invoice INV" in adm.get("/admin/").get_data(as_text=True) and "Unpaid" in adm.get("/admin/").get_data(as_text=True)
    pd = f"/portal/jobs/{lid}/invoice/{iid}?as=hapitech"
    _form(adm, pd, {"action": "paid"}, page=pd)
    _form(adm, pd, {"action": "paid"}, page=pd)
    with app.app_context():
        pays = Payment.query.filter_by(account_id=roid).all()
        assert len(pays) == 1 and float(pays[0].amount_gbp) == 80 and pays[0].ref.startswith("INV-")
    assert "Pay £" not in app.test_client().get(f"/i/{token}").get_data(as_text=True)          # receipt: no button
    # in a dashboard as admin: a clear "where am I" strip with a way back
    assert adm.get("/portal/?as=hapitech").headers["Location"].endswith("/admin/")      # your home = admin overview
    jobs = adm.get("/portal/jobs?as=hapitech").get_data(as_text=True)
    assert "app--admin" in jobs and "Enquiries &amp; jobs" in jobs and "Benchmark runs" in jobs   # inside admin
    assert "Viewing <b>Roland" in adm.get("/portal/?as=rolands").get_data(as_text=True)


def test_quote_accepted_notices_for_clients_and_admin(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead, Quote
    from utils.hapitech_account import get as hapitech
    with app.app_context():
        ro = Account.query.filter_by(slug="rolands").first()
        l = Lead(account_id=ro.id, name="Quinn", status="quoted", title="Decking")
        db.session.add(l); db.session.flush()
        q = Quote(account_id=ro.id, lead_id=l.id, number="Q-0001", items='[{"desc":"Decking","qty":1,"price":300}]', status="sent")
        ht = hapitech()
        hl = Lead(account_id=ht.id, source="request", name="Roland", email="roland@test", for_account_id=ro.id, title="New page", status="quoted")
        db.session.add_all([q, hl]); db.session.flush()
        hq = Quote(account_id=ht.id, lead_id=hl.id, number="Q-0001", items='[{"desc":"Page","qty":1,"price":90}]', status="sent")
        db.session.add(hq); db.session.commit()
        tokens = (q.token, hq.token)
    for tok in tokens:                                   # both customers accept
        cust = app.test_client()
        csrf = re.search(r'name="csrf-token" content="([^"]+)"', cust.get(f"/q/{tok}").get_data(as_text=True)).group(1)
        cust.post(f"/q/{tok}", data={"csrf_token": csrf, "answer": "accept"})
    c = app.test_client(); _login(c, "roland@test")
    home = c.get("/portal/").get_data(as_text=True)
    assert "Quinn accepted your quote" in home and "pick a date" in home.lower() and "alert-dot" in home
    adm = app.test_client(); _login(adm, "admin@test")
    ov = adm.get("/admin/").get_data(as_text=True)
    assert "Roland accepted quote Q-0001" in ov and "ready to start" in ov


def test_job_done_invoice_invoiced_paid_with_bank_transfer(app):
    import datetime as dt
    from models import db
    from models.core import Account
    from models.work import Lead
    with app.app_context():
        a = Account.query.filter_by(slug="rolands").first()
        l = Lead(account_id=a.id, name="Sarah Jones", email="sarah@example.com", status="booked", title="Shelves",
                 start_at=dt.datetime.combine(dt.date.today(), dt.time(9)), days=1)
        db.session.add(l); db.session.commit(); lid = l.id
    c = app.test_client(); _login(c, "roland@test")
    _form(c, "/portal/settings", {"action": "business", "pay_bank": "1", "payment_details": "Sort code 00-00-00\nAccount 12345678",
                                  "pay_link_on": "1", "pay_link_kind": "monzo", "pay_link": "monzo.me/roland"}, page="/portal/settings")
    r = _form(c, f"/portal/jobs/{lid}", {"action": "done"}, page=f"/portal/jobs/{lid}")
    assert r.headers["Location"].endswith(f"/portal/jobs/{lid}/invoice")                  # done -> invoice
    page = f"/portal/jobs/{lid}/invoice"
    _form(c, page, {"desc": "Shelves", "qty": "1", "price": "60", "vat_rate": "0", "action": "send"}, page=page)
    mail = _html_of([m for m in _outbox(app) if "To: sarah@example.com" in m and "Invoice INV" in m][-1])
    assert "monzo.me/roland/60.00" in mail and "Sort code 00-00-00" in mail and "Your reference" in mail
    assert "Thanks! Use the payment link provided" in mail
    with app.app_context():
        assert db.session.get(Lead, lid).stage == "invoiced"
    assert "Sarah Jones" in c.get("/portal/jobs?show=invoiced").get_data(as_text=True)
    assert "Mark paid" in c.get(f"/portal/jobs/{lid}").get_data(as_text=True)
    _form(c, f"/portal/jobs/{lid}", {"action": "paid"}, page=f"/portal/jobs/{lid}")
    with app.app_context():
        assert db.session.get(Lead, lid).stage == "paid"
    assert "Sarah Jones" in c.get("/portal/jobs?show=paid").get_data(as_text=True)
    _form(c, f"/portal/jobs/{lid}", {"action": "receipt"}, page=f"/portal/jobs/{lid}")
    assert any("To: sarah@example.com" in m and "Receipt INV" in m for m in _outbox(app))
