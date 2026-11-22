# routes/lab.py — public HapiTech Lab: published local-AI benchmark results.
import json
import os

from flask import Blueprint, abort, current_app, render_template, send_from_directory

from models import db
from models.bench import BenchPrompt, BenchRun

lab_bp = Blueprint("lab", __name__)


def published_runs():
    return BenchRun.query.filter_by(status="published").order_by(BenchRun.published_at.desc()).all()


def lab_news_items(limit=50):
    """Published runs shaped like AI-news items (credited to HapiTech Lab)."""
    items = []
    for r in published_runs()[:limit]:
        rate = r.pass_rate
        bits = []
        if rate is not None:
            bits.append(f"passed {round(rate * 100)}% of {len(r.results)} attempt{'s' if len(r.results) != 1 else ''}")
        if r.avg("decode_tps"):
            bits.append(f"{r.avg('decode_tps'):.0f} tokens/sec")
        excerpt = r.summary or (f"{r.model.display_name} on our {r.prompt.name.lower()} test: " + ", ".join(bits) + "."
                                if bits else f"{r.model.display_name} on our {r.prompt.name.lower()} test.")
        when = r.published_at or r.created_at
        items.append({
            "id": f"lab-{r.id}", "title": f"{r.model.display_name}: {r.prompt.name}", "link": f"/lab/runs/{r.id}",
            "internal": True, "excerpt": excerpt, "content": "", "image": "",
            "date": when.isoformat() + "+00:00", "source": "HapiTech Lab", "source_id": "hapitech-lab",
            "source_home": "/lab", "cat": "local",
        })
    return items


@lab_bp.route("/lab")
def index():
    prompts = BenchPrompt.query.filter_by(is_current=True).order_by(BenchPrompt.slug).all()
    by_prompt = {}
    for r in published_runs():
        by_prompt.setdefault(r.prompt.slug, []).append(r)
    return render_template("lab/index.html", prompts=[p for p in prompts if p.slug in by_prompt], by_prompt=by_prompt)


@lab_bp.route("/lab/runs/<int:rid>")
def run(rid):
    r = db.session.get(BenchRun, rid)
    if not r or r.status != "published":
        abort(404)
    raw = [json.loads(x.raw) for x in r.results]
    return render_template("lab/run.html", r=r, raw=raw, engine=json.loads(r.engine or "{}"))


@lab_bp.route("/lab/runs/<int:rid>/artefact")
def artefact(rid):
    r = db.session.get(BenchRun, rid)
    if not r or r.status != "published" or not r.artefact_path:
        abort(404)
    d = os.path.join(current_app.config["UPLOAD_ROOT"], "_lab", str(r.id))
    resp = send_from_directory(d, "index.html", mimetype="text/html")
    # model-written code: no same-origin access, no top navigation, no forms
    resp.headers["Content-Security-Policy"] = "sandbox allow-scripts; default-src 'self' 'unsafe-inline' data: blob:"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
