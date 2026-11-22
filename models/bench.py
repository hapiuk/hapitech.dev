# models/bench.py — HapiTech Lab: local AI benchmark models, versioned prompts, runs and results.
from . import db
from .core import TimestampMixin, utcnow


class BenchModel(TimestampMixin, db.Model):
    __tablename__ = "bench_models"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False)       # e.g. unsloth/Qwen3.8-27B-GGUF
    display_name = db.Column(db.String(160), nullable=False)
    maintainer = db.Column(db.String(120))
    quant = db.Column(db.String(80))
    file_size_bytes = db.Column(db.BigInteger)
    native_ctx = db.Column(db.Integer)
    supports_vision = db.Column(db.Boolean)
    supports_tools = db.Column(db.Boolean)
    source_url = db.Column(db.String(500))
    role = db.Column(db.String(160))
    blurb = db.Column(db.Text)
    notes = db.Column(db.Text)
    hardware_profile = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="active")  # active | candidate | blocked | retired
    runs = db.relationship("BenchRun", back_populates="model", lazy=True)


class BenchPrompt(db.Model):
    """Versioned: editing creates a new row with version+1; runs keep pointing at the version used."""
    __tablename__ = "bench_prompts"
    __table_args__ = (db.UniqueConstraint("slug", "version", name="uq_prompt_slug_version"),)
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), nullable=False, index=True)          # e.g. 02-tool-calling
    version = db.Column(db.Integer, nullable=False, default=1)
    is_current = db.Column(db.Boolean, nullable=False, default=True)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(60))
    kind = db.Column(db.String(60))
    description = db.Column(db.Text)
    prompt_text = db.Column(db.Text, nullable=False)
    pass_criteria = db.Column(db.Text)
    grading = db.Column(db.String(40))
    max_tokens = db.Column(db.Integer)
    repeats = db.Column(db.Integer)
    config = db.Column(db.Text, nullable=False, default="{}")    # remaining JSON fields from the prompt file
    fixtures = db.Column(db.Text, nullable=False, default="{}")  # {relative_path: file text}
    changelog = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    runs = db.relationship("BenchRun", back_populates="prompt", lazy=True)


class BenchRun(db.Model):
    __tablename__ = "bench_runs"
    id = db.Column(db.Integer, primary_key=True)
    prompt_id = db.Column(db.Integer, db.ForeignKey("bench_prompts.id"), nullable=False, index=True)
    model_id = db.Column(db.Integer, db.ForeignKey("bench_models.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime)
    context_length = db.Column(db.Integer)
    engine = db.Column(db.Text, nullable=False, default="{}")
    harness = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(20), nullable=False, default="draft")   # draft | published | withdrawn
    summary = db.Column(db.Text)                                        # plain-English note for the public page
    notes = db.Column(db.Text)                                          # private
    artefact_path = db.Column(db.String(300))                           # e.g. an HTML game build
    source_file = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    published_at = db.Column(db.DateTime)
    prompt = db.relationship("BenchPrompt", back_populates="runs")
    model = db.relationship("BenchModel", back_populates="runs")
    results = db.relationship("BenchResult", back_populates="run", lazy=True, cascade="all, delete-orphan",
                              order_by="BenchResult.repeat_n")

    @property
    def pass_rate(self):
        graded = [r for r in self.results if r.passed is not None]
        return None if not graded else sum(1 for r in graded if r.passed) / len(graded)

    def avg(self, attr):
        vals = [getattr(r, attr) for r in self.results if getattr(r, attr) is not None]
        return sum(vals) / len(vals) if vals else None


class BenchResult(db.Model):
    __tablename__ = "bench_results"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("bench_runs.id"), nullable=False, index=True)
    repeat_n = db.Column(db.Integer, nullable=False, default=1)
    passed = db.Column(db.Boolean)
    score = db.Column(db.Float)
    ttft_ms = db.Column(db.Float)
    prefill_tps = db.Column(db.Float)
    decode_tps = db.Column(db.Float)
    prompt_tokens = db.Column(db.Integer)
    completion_tokens = db.Column(db.Integer)
    total_seconds = db.Column(db.Float)
    raw = db.Column(db.Text, nullable=False, default="{}")       # the full original JSONL record
    run = db.relationship("BenchRun", back_populates="results")
