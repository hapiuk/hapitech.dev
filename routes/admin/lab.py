# routes/admin/lab.py — HapiTech Lab admin: models, versioned prompts, benchmark runs.
import datetime as dt
import json
import os

from flask import Response, abort, current_app, flash, redirect, render_template, request, url_for

from models import db
from models.bench import BenchModel, BenchPrompt, BenchResult, BenchRun
from utils.bench import ParseError, build_run, group_runs, parse_jsonl

from . import admin_bp

MAX_UPLOAD = 8 * 1024 * 1024


# ---------------------------------------------------------------- models

MODEL_FIELDS = ("slug", "display_name", "maintainer", "quant", "source_url", "role", "blurb", "notes",
                "hardware_profile", "status")


@admin_bp.route("/lab/models")
def bench_models():
    rows = BenchModel.query.order_by(db.case((BenchModel.status == "active", 0), else_=1), BenchModel.display_name).all()
    return render_template("admin/lab/models.html", rows=rows)


@admin_bp.route("/lab/models/new", methods=["GET", "POST"])
@admin_bp.route("/lab/models/<int:mid>", methods=["GET", "POST"])
def bench_model(mid=None):
    m = (db.session.get(BenchModel, mid) or abort(404)) if mid else BenchModel(status="candidate")
    if request.method == "POST":
        f = request.form
        for k in MODEL_FIELDS:
            if k in f:
                setattr(m, k, (f.get(k) or "").strip() or None)
        for k in ("native_ctx", "file_size_bytes"):
            v = (f.get(k) or "").replace(",", "").strip()
            setattr(m, k, int(v) if v.isdigit() else None)
        for k in ("supports_vision", "supports_tools"):
            setattr(m, k, {"yes": True, "no": False}.get(f.get(k)))
        if not m.slug or not m.display_name:
            flash("A model needs an ID and a display name.", "err")
            return render_template("admin/lab/model_form.html", m=m)
        clash = BenchModel.query.filter(BenchModel.slug == m.slug, BenchModel.id != (m.id or 0)).first()
        if clash:
            flash("Another model already uses that ID.", "err")
            return render_template("admin/lab/model_form.html", m=m)
        m.status = m.status if m.status in ("active", "candidate", "blocked", "retired") else "candidate"
        if not mid:
            db.session.add(m)
        db.session.commit()
        flash("Model saved.", "ok")
        return redirect(url_for("admin.bench_models"))
    return render_template("admin/lab/model_form.html", m=m)


# ---------------------------------------------------------------- prompts

@admin_bp.route("/lab/prompts")
def bench_prompts():
    rows = BenchPrompt.query.filter_by(is_current=True).order_by(BenchPrompt.slug).all()
    run_counts = dict(db.session.query(BenchPrompt.slug, db.func.count(BenchRun.id))
                      .join(BenchRun, BenchRun.prompt_id == BenchPrompt.id).group_by(BenchPrompt.slug).all())
    return render_template("admin/lab/prompts.html", rows=rows, run_counts=run_counts)


def _prompt_or_404(slug, version=None):
    q = BenchPrompt.query.filter_by(slug=slug)
    p = q.filter_by(version=version).first() if version else q.filter_by(is_current=True).first()
    return p or abort(404)


@admin_bp.route("/lab/prompts/<slug>")
def bench_prompt(slug):
    v = request.args.get("v", type=int)
    p = _prompt_or_404(slug, v)
    versions = BenchPrompt.query.filter_by(slug=slug).order_by(BenchPrompt.version.desc()).all()
    runs = (BenchRun.query.join(BenchPrompt).filter(BenchPrompt.slug == slug)
            .order_by(BenchRun.created_at.desc()).all())
    return render_template("admin/lab/prompt.html", p=p, versions=versions, runs=runs,
                           fixtures=json.loads(p.fixtures or "{}"), config=json.loads(p.config or "{}"))


def _export(p: BenchPrompt) -> dict:
    out = {"id": p.slug, "name": p.name, "category": p.category, "kind": p.kind, "description": p.description,
           "prompt": p.prompt_text, "max_tokens": p.max_tokens, "repeats": p.repeats, "grading": p.grading,
           "pass_criteria": p.pass_criteria}
    out.update(json.loads(p.config or "{}"))
    out["_hapitech"] = {"version": p.version, "exported_at": dt.datetime.utcnow().isoformat() + "Z"}
    return {k: v for k, v in out.items() if v is not None}


@admin_bp.route("/lab/prompts/<slug>.json")
def bench_prompt_json(slug):
    p = _prompt_or_404(slug, request.args.get("v", type=int))
    return Response(json.dumps(_export(p), indent=2, ensure_ascii=False), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{p.slug}.v{p.version}.json"'})


@admin_bp.route("/lab/prompts/new", methods=["GET", "POST"])
@admin_bp.route("/lab/prompts/<slug>/edit", methods=["GET", "POST"])
def bench_prompt_edit(slug=None):
    cur = _prompt_or_404(slug) if slug else None
    if request.method == "POST":
        f = request.form
        new_slug = slug or (f.get("slug") or "").strip()
        if not new_slug or not (f.get("prompt_text") or "").strip() or not (f.get("name") or "").strip():
            flash("A prompt needs an ID, a name and the prompt text.", "err")
            return render_template("admin/lab/prompt_form.html", p=cur, f=f)
        if not slug and BenchPrompt.query.filter_by(slug=new_slug).first():
            flash("That ID is already used.", "err")
            return render_template("admin/lab/prompt_form.html", p=cur, f=f)
        try:
            config = json.loads(f.get("config") or "{}")
            if not isinstance(config, dict):
                raise ValueError
        except ValueError:
            flash("Extra settings must be a JSON object, e.g. {\"repeat_mode\": \"sequential\"}.", "err")
            return render_template("admin/lab/prompt_form.html", p=cur, f=f)
        if cur:
            cur.is_current = False
        p = BenchPrompt(
            slug=new_slug, version=(cur.version + 1) if cur else 1, is_current=True,
            name=f["name"].strip(), category=(f.get("category") or "").strip() or None,
            kind=(f.get("kind") or "").strip() or None, description=(f.get("description") or "").strip() or None,
            prompt_text=f["prompt_text"], pass_criteria=(f.get("pass_criteria") or "").strip() or None,
            grading=f.get("grading") or None, max_tokens=f.get("max_tokens", type=int),
            repeats=f.get("repeats", type=int), config=json.dumps(config, indent=1),
            fixtures=cur.fixtures if cur else "{}", changelog=(f.get("changelog") or "").strip() or None)
        db.session.add(p)
        db.session.commit()
        flash(f"Saved as version {p.version}. Earlier runs still point at the version they used.", "ok")
        return redirect(url_for("admin.bench_prompt", slug=p.slug))
    return render_template("admin/lab/prompt_form.html", p=cur, f=None)


# ---------------------------------------------------------------- runs

@admin_bp.route("/lab/runs")
def bench_runs():
    status = request.args.get("status", "all")
    q = BenchRun.query
    if status != "all":
        q = q.filter_by(status=status)
    rows = q.order_by(BenchRun.created_at.desc(), BenchRun.id.desc()).limit(300).all()
    counts = dict(db.session.query(BenchRun.status, db.func.count()).group_by(BenchRun.status).all())
    return render_template("admin/lab/runs.html", rows=rows, status=status, counts=counts)


@admin_bp.route("/lab/runs/new", methods=["GET", "POST"])
def bench_run_new():
    if request.method == "POST":
        text, fname = (request.form.get("jsonl") or "").strip(), None
        up = request.files.get("file")
        if up and up.filename:
            raw = up.read(MAX_UPLOAD + 1)
            if len(raw) > MAX_UPLOAD:
                flash("That file is over 8 MB.", "err")
                return render_template("admin/lab/run_new.html", jsonl=text)
            text, fname = raw.decode("utf-8", "replace"), up.filename[:200]
        try:
            groups = group_runs(parse_jsonl(text))
            runs = [build_run(g, status="draft", source_file=fname or "pasted") for g in groups]
        except ParseError as e:
            flash(str(e), "err")
            return render_template("admin/lab/run_new.html", jsonl=text)
        for r in runs:
            db.session.add(r)
        db.session.commit()
        flash(f"{len(runs)} draft run{'s' if len(runs) != 1 else ''} created. Check the numbers, then publish.", "ok")
        if len(runs) == 1:
            return redirect(url_for("admin.bench_run", rid=runs[0].id))
        return redirect(url_for("admin.bench_runs", status="draft"))
    return render_template("admin/lab/run_new.html", jsonl="")


def _artefact_dir(run: BenchRun):
    d = os.path.join(current_app.config["UPLOAD_ROOT"], "_lab", str(run.id))
    os.makedirs(d, exist_ok=True)
    return d


@admin_bp.route("/lab/runs/<int:rid>", methods=["GET", "POST"])
def bench_run(rid):
    run = db.session.get(BenchRun, rid) or abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            run.summary = (request.form.get("summary") or "").strip() or None
            run.notes = (request.form.get("notes") or "").strip() or None
            for res in run.results:
                v = request.form.get(f"passed_{res.id}")
                if v in ("yes", "no", "unknown"):
                    res.passed = {"yes": True, "no": False}.get(v)
            flash("Saved.", "ok")
        elif action == "publish":
            run.status, run.published_at = "published", dt.datetime.utcnow()
            flash("Published. It's now on the public results page and in AI news.", "ok")
        elif action == "withdraw":
            run.status = "withdrawn"
            flash("Withdrawn. It's hidden from the public pages, and kept here.", "ok")
        elif action == "draft":
            run.status = "draft"
        elif action == "delete" and run.status != "published":
            db.session.delete(run)
            db.session.commit()
            flash("Draft deleted.", "ok")
            return redirect(url_for("admin.bench_runs"))
        elif action == "artefact":
            up = request.files.get("artefact")
            if up and up.filename.lower().endswith((".html", ".htm")):
                raw = up.read(MAX_UPLOAD + 1)
                if len(raw) > MAX_UPLOAD:
                    flash("That file is over 8 MB.", "err")
                else:
                    with open(os.path.join(_artefact_dir(run), "index.html"), "wb") as fh:
                        fh.write(raw)
                    run.artefact_path = f"_lab/{run.id}/index.html"
                    flash("Artefact attached. It opens in a locked-down sandbox on the public page.", "ok")
            else:
                flash("Attach a single .html file (e.g. the game the model built).", "err")
        db.session.commit()
        return redirect(url_for("admin.bench_run", rid=rid))
    raw_first = json.loads(run.results[0].raw) if run.results else {}
    return render_template("admin/lab/run.html", run=run, raw_first=raw_first)
