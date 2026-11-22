# routes/pwa.py — "install as an app" for the dashboards.
# Each client's portal installs under THEIR name and logo (not HapiTech's); the admin installs as HapiTech.
# Manifests and icons contain only public branding, so they're served without login.
import json
import os

from flask import Blueprint, abort, current_app, make_response, send_file
from PIL import Image

from models.core import Account

pwa_bp = Blueprint("pwa", __name__)

ICON_SIZES = (192, 512, 180)
HAPITECH = {"slug": "_hapitech", "name": "HapiTech Admin", "short": "HapiTech", "logo": "media/logo.png",
            "colour": "#0c0e12", "start": "/admin/", "scope": "/admin/"}


def _brand(slug):
    if slug == "_hapitech":
        return HAPITECH
    a = Account.query.filter_by(slug=slug, kind="client").first()
    if not a or a.status == "archived":
        abort(404)
    short = a.name
    while len(short) > 14 and " " in short:          # trim whole words: "Ray G Handyman Services" -> "Ray G Handyman"
        short = short.rsplit(" ", 1)[0]
    return {"slug": a.slug, "name": a.name, "short": short[:14],
            "logo": a.logo_path or HAPITECH["logo"], "colour": a.brand_colour or "#0c0e12",
            "start": "/portal/", "scope": "/portal/"}


def _icon_path(b, size, maskable=False):
    """Square PNG made from the logo: white tile, logo centred inside the 'safe zone'."""
    src = os.path.join(current_app.static_folder, b["logo"])
    out_dir = os.path.join(current_app.config["UPLOAD_ROOT"], "_icons")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{b['slug']}-{size}{'-m' if maskable else ''}.png")
    if os.path.exists(out) and os.path.exists(src) and os.path.getmtime(out) >= os.path.getmtime(src):
        return out
    tile = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    try:
        logo = Image.open(src).convert("RGBA")
        box = int(size * (0.62 if maskable else 0.78))       # maskable icons get cropped to a circle
        logo.thumbnail((box, box), Image.LANCZOS)
        tile.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
    except (OSError, ValueError):
        pass
    tile.convert("RGB").save(out, "PNG", optimize=True)
    return out


@pwa_bp.route("/app/<slug>/icon-<int:size>.png")
@pwa_bp.route("/app/<slug>/icon-<int:size>-<variant>.png")
def icon(slug, size, variant=None):
    if size not in ICON_SIZES:
        abort(404)
    resp = make_response(send_file(_icon_path(_brand(slug), size, maskable=variant == "maskable"), mimetype="image/png"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@pwa_bp.route("/app/<slug>/manifest.webmanifest")
def manifest(slug):
    b = _brand(slug)
    data = {
        "name": b["name"], "short_name": b["short"], "id": b["start"] + ("?app=" + b["slug"]),
        "start_url": b["start"], "scope": b["scope"], "display": "standalone",
        "background_color": "#0c0e12", "theme_color": b["colour"],
        "icons": [
            {"src": f"/app/{b['slug']}/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": f"/app/{b['slug']}/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": f"/app/{b['slug']}/icon-512-maskable.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }
    resp = make_response(json.dumps(data))
    resp.headers["Content-Type"] = "application/manifest+json"
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


SW = """// Minimal service worker: makes the dashboard installable. Always goes to the network
// (dashboards show live data), with a simple offline message if there's no connection.
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (e) {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(function () {
    return new Response('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<body style="font-family:system-ui;padding:40px 20px;text-align:center;background:#0c0e12;color:#eceef2">' +
      '<h1 style="font-size:1.4rem">You\\'re offline</h1><p>Check your signal and try again.</p></body>',
      {headers: {'Content-Type': 'text/html'}});
  }));
});
"""


@pwa_bp.route("/portal/sw.js")
@pwa_bp.route("/admin/sw.js")
def service_worker():
    resp = make_response(SW)
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Cache-Control"] = "no-cache"
    return resp
