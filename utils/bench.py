# utils/bench.py — HapiTech Lab benchmark data: importers, JSONL parsing and model matching.
import datetime as dt
import json
import os
import re

from models import db
from models.bench import BenchModel, BenchPrompt, BenchResult, BenchRun

PROMPT_CORE_FIELDS = {"id", "name", "category", "kind", "description", "prompt", "pass_criteria", "grading",
                      "max_tokens", "repeats"}
FIXTURE_REF_FIELDS = ("tools_file", "expected_results_file", "fixture_root", "test_file", "needle_file", "schema")
MAX_FIXTURE_BYTES = 400_000


# ---------------------------------------------------------------- models

def _norm(name: str) -> str:
    """'unsloth/Qwen3.8-27B-GGUF' and 'Qwen3.8-27B-UD-IQ3_XXS' both -> 'qwen3.8-27b'."""
    n = (name or "").split("/")[-1].lower()
    n = re.sub(r"-gguf$", "", n)
    n = re.sub(r"-(ud-)?(iq|q)\d.*$", "", n)
    return n


def find_model(name: str):
    m = BenchModel.query.filter_by(slug=name).first()
    if m:
        return m
    target = _norm(name)
    for cand in BenchModel.query.all():
        if _norm(cand.slug) == target:
            return cand
    return None


def import_models(path: str) -> int:
    if not os.path.exists(path):
        return 0
    data = json.load(open(path, encoding="utf-8"))
    added = 0
    for m in data.get("models", []):
        if m.get("id") in ("test-model",) or BenchModel.query.filter_by(slug=m["id"]).first():
            continue
        status = {"complete": "active", "incomplete": "blocked"}.get(m.get("download_status"), "candidate")
        db.session.add(BenchModel(
            slug=m["id"], display_name=m.get("display_name") or m["id"], maintainer=m.get("maintainer"),
            quant=m.get("quant"), file_size_bytes=m.get("file_size_bytes"), native_ctx=m.get("native_context_length"),
            supports_vision=m.get("supports_vision"), supports_tools=m.get("supports_tools"),
            source_url=m.get("source_url"), role=m.get("role"), blurb=m.get("blurb"), notes=m.get("notes"),
            hardware_profile=m.get("hardware_profile"), status=status))
        added += 1
    db.session.flush()
    return added


# ---------------------------------------------------------------- prompts

def _read_fixtures(prompt: dict, base_dir: str) -> dict:
    """Collect the text of every fixture file a prompt references (paths relative to the bench dir)."""
    out = {}
    for key in FIXTURE_REF_FIELDS:
        rel = prompt.get(key)
        if not isinstance(rel, str) or not rel.startswith("fixtures/"):
            continue
        full = os.path.join(base_dir, rel)
        paths = []
        if os.path.isdir(full):
            for root, _, files in os.walk(full):
                paths += [os.path.join(root, f) for f in files]
        elif os.path.isfile(full):
            paths = [full]
        for p in sorted(paths):
            if os.path.getsize(p) > MAX_FIXTURE_BYTES:
                out[os.path.relpath(p, base_dir)] = f"[file too large to store: {os.path.getsize(p)} bytes]"
                continue
            try:
                out[os.path.relpath(p, base_dir)] = open(p, encoding="utf-8").read()
            except UnicodeDecodeError:
                out[os.path.relpath(p, base_dir)] = "[binary file]"
    return out


def import_prompts(prompts_dir: str, fixtures_dir: str, extra_prompt_dirs=()) -> int:
    if not os.path.isdir(prompts_dir):
        return 0
    base = os.path.dirname(prompts_dir.rstrip("/"))
    added = 0
    for path in sorted(os.listdir(prompts_dir)):
        if not path.endswith(".json"):
            continue
        p = json.load(open(os.path.join(prompts_dir, path), encoding="utf-8"))
        slug = p.get("id") or path[:-5]
        if BenchPrompt.query.filter_by(slug=slug).first():
            continue
        fixtures = _read_fixtures(p, base)
        # the original prompt folder (docs/local_ai_benchmark_prompts/<slug>/) as extra reference material
        for extra in extra_prompt_dirs:
            d = os.path.join(extra, slug)
            if os.path.isdir(d):
                for root, _, files in os.walk(d):
                    for f in sorted(files):
                        fp = os.path.join(root, f)
                        if os.path.getsize(fp) <= MAX_FIXTURE_BYTES:
                            try:
                                fixtures["original/" + os.path.relpath(fp, extra)] = open(fp, encoding="utf-8").read()
                            except UnicodeDecodeError:
                                pass
        config = {k: v for k, v in p.items() if k not in PROMPT_CORE_FIELDS}
        db.session.add(BenchPrompt(
            slug=slug, version=1, is_current=True, name=p.get("name") or slug, category=p.get("category"),
            kind=p.get("kind"), description=p.get("description"), prompt_text=p.get("prompt") or "",
            pass_criteria=p.get("pass_criteria"), grading=p.get("grading"), max_tokens=p.get("max_tokens"),
            repeats=p.get("repeats"), config=json.dumps(config, indent=1), fixtures=json.dumps(fixtures),
            changelog="Imported from ai-benchmarks/prompts"))
        added += 1
    db.session.flush()
    return added


# ---------------------------------------------------------------- results

class ParseError(ValueError):
    pass


def parse_jsonl(text: str) -> list[dict]:
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ParseError(f"Line {n} isn't valid JSON ({e.msg}).")
    if not rows:
        raise ParseError("The file is empty.")
    for n, r in enumerate(rows, 1):
        for k in ("test_id", "model"):
            if not r.get(k):
                raise ParseError(f"Record {n} has no '{k}'.")
    return rows


def group_runs(rows: list[dict]) -> list[list[dict]]:
    """Split records into runs: a run starts at repeat 1 (or when test/model changes)."""
    runs, cur = [], []
    for r in rows:
        if cur and (r.get("repeat", 1) == 1 or r["test_id"] != cur[-1]["test_id"] or r["model"] != cur[-1]["model"]):
            runs.append(cur)
            cur = []
        cur.append(r)
    if cur:
        runs.append(cur)
    return runs


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def result_from_record(r: dict) -> BenchResult:
    pre, dec = r.get("prefill") or {}, r.get("decode") or {}
    tel = (r.get("backend_telemetry") or [{}])[0] if r.get("backend_telemetry") else {}
    passed = r.get("passed") if isinstance(r.get("passed"), bool) else None
    if passed is None and isinstance(r.get("status"), str):          # older Hermes format: "PASS"/"FAIL"
        passed = {"PASS": True, "FAIL": False}.get(r["status"].strip().upper())
    return BenchResult(
        repeat_n=r.get("repeat") or 1,
        passed=passed,
        score=_num(r.get("score")),
        ttft_ms=_num(r.get("ttft_ms")) or _num(tel.get("ttft_ms")),
        prefill_tps=_num(pre.get("tokens_per_second")) or _num(tel.get("prefill_tokens_per_second")),
        decode_tps=_num(dec.get("tokens_per_second")) or _num(tel.get("decode_tokens_per_second")),
        prompt_tokens=pre.get("prompt_tokens") or tel.get("prompt_tokens"),
        completion_tokens=dec.get("completion_tokens") or tel.get("completion_tokens"),
        total_seconds=_num(r.get("total_seconds")) or _num(r.get("duration_seconds")),
        raw=json.dumps(r),
    )


def build_run(records: list[dict], status="draft", source_file=None):
    """Create a BenchRun (+results) from one group of records. Raises ParseError if the prompt
    or model isn't known yet."""
    with db.session.no_autoflush:
        return _build_run(records, status, source_file)


def _build_run(records, status, source_file):
    first = records[0]
    prompt = BenchPrompt.query.filter_by(slug=first["test_id"], is_current=True).first()
    if not prompt:
        raise ParseError(f"Unknown test '{first['test_id']}'. Add the prompt first (Admin → Benchmarks → Prompts).")
    model = find_model(first["model"])
    if not model:
        raise ParseError(f"Unknown model '{first['model']}'. Add it first (Admin → Benchmarks → Models).")
    ts = first.get("ts")
    started = None
    if ts:
        try:
            started = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    run = BenchRun(prompt=prompt, model=model, started_at=started, context_length=first.get("context_length"),
                   engine=json.dumps(first.get("engine") or {}), harness=json.dumps(first.get("harness") or {}),
                   status=status, source_file=source_file,
                   summary=(first.get("details") or None) if len(records) == 1 else None,
                   published_at=dt.datetime.utcnow() if status == "published" else None)
    run.results = [result_from_record(r) for r in records]
    return run


def import_published(published_dir: str) -> int:
    if not os.path.isdir(published_dir):
        return 0
    def key(r):
        return (r.get("test_id"), r.get("model"), r.get("ts"), r.get("repeat"))

    seen = {key(json.loads(x.raw)) for x in BenchResult.query.all()}
    added = 0
    for fname in sorted(os.listdir(published_dir)):
        if not fname.endswith(".jsonl"):
            continue
        rows = parse_jsonl(open(os.path.join(published_dir, fname), encoding="utf-8").read())
        for group in group_runs(rows):
            if key(group[0]) in seen:
                continue        # already imported
            try:
                db.session.add(build_run(group, status="published", source_file=fname))
                added += 1
            except ParseError as e:
                print(f"[import-bench] skipped a run in {fname}: {e}")
    db.session.flush()
    return added
