# cli.py — operational commands (run with `flask <command>` from the app folder).
#
#   flask deploy                    backup DB, bring migrations up to date (used by the server one-liner)
#   flask create-admin EMAIL        make EMAIL an admin (login is by emailed code, no passwords)
#   flask setup-clients             fill in Roland's / Ray G account details (idempotent)
#   flask import-site-reviews SLUG PATH_TO_CLIENT_SITE
#                                   import the reviews hard-coded in a client site's app.py (idempotent)
#   flask import-bench PATH         import benchmark models/prompts/fixtures/published results (idempotent)
#   flask seed-dev                  LOCAL ONLY: demo logins + data (codes show on screen locally)
import ast
import datetime as dt
import glob
import json
import os
import secrets
import shutil

import click
from flask import current_app

from models import db


def register_cli(app):
    for cmd in (deploy, create_admin, setup_clients, import_site_reviews, import_bench, seed_dev, tick):
        app.cli.add_command(cmd)


# ---------------------------------------------------------------- deploy

def _sqlite_path():
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        return None
    p = uri[len("sqlite:///"):]
    return p if os.path.isabs(p) else os.path.join(current_app.instance_path, p)


@click.command("deploy")
@click.option("--no-backup", is_flag=True)
def deploy(no_backup):
    """Back up the database, then apply any pending migrations."""
    from flask_migrate import stamp, upgrade
    from sqlalchemy import inspect

    db_path = _sqlite_path()
    if db_path and os.path.exists(db_path) and not no_backup:
        bdir = os.path.join(current_app.instance_path, "backups")
        os.makedirs(bdir, exist_ok=True)
        dest = os.path.join(bdir, f"{os.path.basename(db_path)}.{dt.datetime.utcnow():%Y%m%dT%H%M%SZ}")
        shutil.copy2(db_path, dest)
        click.echo(f"Backed up database -> {dest}")
    elif not db_path:
        click.echo("Not SQLite: take a database backup with your usual tool before continuing.")

    tables = set(inspect(db.engine).get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        # Older installs created tables with create_all() and were never stamped.
        rev = ("c4d5e6f7a8b9" if "monthly_payment_status" in tables else
               "ba2985044551" if "clients" in tables else "e31e40d8f497")
        click.echo(f"Database was never stamped; marking it as revision {rev}.")
        stamp(revision=rev)
    upgrade()
    click.echo("Database is up to date.")


# ---------------------------------------------------------------- users

@click.command("create-admin")
@click.argument("email")
@click.option("--name", default="Aaron")
def create_admin(email, name):
    """Make EMAIL an admin (creates the user if needed). Log in with an emailed code; no password."""
    from models.core import User
    email = email.strip().lower()
    u = User.query.filter(db.func.lower(User.email) == email).first()
    if u is None:
        u = User(email=email, username=email, name=name, role="admin")
        db.session.add(u)
    u.role, u.is_active_flag, u.password_hash = "admin", True, ""
    db.session.commit()
    click.echo(f"Admin ready: {email}")


# ---------------------------------------------------------------- clients

CLIENT_DETAILS = {
    # matched by domain; safe to re-run
    "rolandshandyman.co.uk": dict(
        name="Roland's Handyman", slug="rolands-handyman", trade="Handyman & property maintenance",
        town="West Midlands", contact_name="Roland", contact_phone="+447554585833",
        google_profile_url="https://g.page/r/CexidGdXUTMsEAE/review",
        logo_path="media/clients/rolandshandyman.png", brand_colour="#f97316"),
    "rayghandymanservice.co.uk": dict(
        name="Ray G Handyman Services", slug="ray-g-handyman", trade="Home improvement & renovation",
        town="Wolverhampton", contact_name="Ray", contact_phone="+447379195256",
        google_profile_url="https://g.page/r/CeR53HEINwUDEAE/review",
        logo_path="media/clients/rayg.png", brand_colour="#dc2626"),
}


@click.command("setup-clients")
def setup_clients():
    """Fill in Roland's and Ray G's account details (creates the accounts if missing)."""
    from models.core import Account
    for domain, d in CLIENT_DETAILS.items():
        acct = Account.query.filter_by(domain=domain).first() or Account.query.filter_by(slug=d["slug"]).first()
        if acct is None:
            acct = Account(domain=domain, kind="client", status="active")
            db.session.add(acct)
        for k, v in d.items():
            if k == "slug" and Account.query.filter(Account.slug == v, Account.id != acct.id).first():
                continue
            setattr(acct, k, v)
        acct.domain = domain
        db.session.flush()
        from utils.content_blocks import ensure_blocks
        ensure_blocks(acct, None)
    db.session.commit()
    click.echo("Client accounts (and their editable website blocks) up to date: " + ", ".join(d["slug"] for d in CLIENT_DETAILS.values()))


def _extract_list(path, var="reviews"):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == var for t in node.targets):
            return ast.literal_eval(node.value)
    raise click.ClickException(f"No `{var} = [...]` list found in {path}")


@click.command("import-site-reviews")
@click.argument("slug")
@click.argument("site_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--source", default="google", show_default=True)
def import_site_reviews(slug, site_dir, source):
    """Import the reviews list from a client site's app.py (photos copied from static/img/reviews)."""
    from models.content import Media
    from models.core import Account
    from models.reviews import Review
    from utils.uploads import account_dir
    acct = Account.query.filter_by(slug=slug).first()
    if not acct:
        raise click.ClickException(f"No account with slug {slug}. Run `flask setup-clients` first.")
    reviews = _extract_list(os.path.join(site_dir, "app.py"))
    added = 0
    for i, r in enumerate(reviews):
        key = f"site-import:{r['name'].strip().lower()}"
        if Review.query.filter_by(account_id=acct.id, source=r.get("source", source), external_id=key).first():
            continue
        photo_ids = []
        for ph in r.get("photos", []):
            src = os.path.join(site_dir, "static", "img", "reviews", ph)
            if not os.path.exists(src):
                continue
            dest_dir = account_dir(acct)
            fname = f"review-{secrets.token_hex(6)}{os.path.splitext(ph)[1].lower()}"
            shutil.copy2(src, os.path.join(dest_dir, fname))
            m = Media(account_id=acct.id, file_path=f"{acct.slug}/{fname}", alt=f"Photo from {r['name']}'s review")
            db.session.add(m)
            db.session.flush()
            photo_ids.append(m.id)
        db.session.add(Review(
            account_id=acct.id, source=r.get("source", source), external_id=key,
            source_url=acct.google_profile_url, author_name=r["name"].strip(), rating=int(r.get("rating", 5)),
            body=r.get("text", "").strip(), photos=json.dumps(photo_ids), status="published",
            verified=False, sort_hint=i, reviewed_at=None))   # real date unknown: never invent one
        added += 1
    db.session.commit()
    click.echo(f"{acct.name}: {added} new review(s) imported, {len(reviews) - added} already present.")


# ---------------------------------------------------------------- benchmarks

@click.command("import-bench")
@click.argument("bench_dir", type=click.Path(exists=True, file_okay=False))
def import_bench(bench_dir):
    """Import ai-benchmarks/{models.json,prompts,fixtures,published} into the database."""
    from utils.bench import import_models, import_prompts, import_published
    m = import_models(os.path.join(bench_dir, "models.json"))
    p = import_prompts(os.path.join(bench_dir, "prompts"), os.path.join(bench_dir, "fixtures"),
                       extra_prompt_dirs=glob.glob("/mnt/data/Hapitech_AI/docs/local_ai_benchmark_prompts"))
    r = import_published(os.path.join(bench_dir, "published"))
    db.session.commit()
    click.echo(f"Models: {m} new · Prompts: {p} new · Runs: {r} new")


# ---------------------------------------------------------------- local demo

@click.command("seed-dev")
@click.option("--clients-dir", default="/mnt/data/Hapitech_AI/projects/clients", show_default=True)
@click.option("--bench-dir", default=None, help="Defaults to <instance>/bench-source")
def seed_dev(clients_dir, bench_dir):
    """LOCAL ONLY. Demo logins (random passwords) + client data for reviewing the build."""
    from models.core import AddOn, Account, Job, Note, Subscription, User
    if current_app.config.get("MAIL_MODE") != "log" or not (os.getenv("FLASK_DEBUG") == "1"):
        raise click.ClickException("seed-dev only runs locally (FLASK_DEBUG=1 and MAIL_MODE=log).")
    ctx = click.get_current_context()
    ctx.invoke(setup_clients)
    lines = [f"# HapiTech local logins — generated {dt.datetime.now():%Y-%m-%d %H:%M}. Local only; never commit.",
             "# Log in at http://127.0.0.1:5077 via 'Client login': enter the email, and in local test mode",
             "# the 6-digit code is shown right there (nothing is really emailed).", ""]
    people = [("aaron@hapitech.dev", "Aaron", "admin", None),
              ("roland@demo.local", "Roland", "owner", "rolands-handyman"),
              ("ray@demo.local", "Ray", "owner", "ray-g-handyman")]
    for email, name, role, slug in people:
        u = User.query.filter_by(email=email).first()
        if u is None:
            u = User(email=email, username=email, name=name, role=role)
            db.session.add(u)
        u.name, u.role, u.is_active_flag, u.password_hash = name, role, True, ""
        u.account = Account.query.filter_by(slug=slug).first() if slug else None
        lines.append(f"{role:6}  {email:24}" + (f"   ({slug})" if slug else ""))
    db.session.commit()

    for slug, site in (("rolands-handyman", "rolandshandyman.co.uk"), ("ray-g-handyman", "rayghandymanservice.co.uk")):
        acct = Account.query.filter_by(slug=slug).first()
        if not acct.addon():
            db.session.add(AddOn(account_id=acct.id, kind="reviews_updates", status="trial",
                                 trial_ends_at=dt.date.today() + dt.timedelta(days=30)))
        if not acct.subscriptions:
            db.session.add(Subscription(account_id=acct.id, title="Hosting & maintenance", amount_gbp=0,
                                        interval="monthly", status="active",
                                        next_due=dt.date.today().replace(day=1) + dt.timedelta(days=32)))
        if not acct.notes_log:
            db.session.add(Note(account_id=acct.id, body="Demo note: site launched and handed over."))
        db.session.commit()
        site_dir = os.path.join(clients_dir, site)
        if os.path.isdir(site_dir):
            ctx.invoke(import_site_reviews, slug=slug, site_dir=site_dir, source="google")
            from utils.content_blocks import ensure_blocks
            ensure_blocks(acct, site_dir)
            db.session.commit()

    bench = bench_dir or os.path.join(current_app.instance_path, "bench-source")
    if os.path.isdir(bench):
        ctx.invoke(import_bench, bench_dir=bench)

    path = os.path.join(current_app.instance_path, "dev-credentials.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)
    click.echo("\n".join(lines[4:]))
    click.echo(f"\nSaved to {path}")


@click.command("tick")
def tick():
    """Run background jobs now (reminders, retention). They also run automatically every few minutes."""
    from utils.tasks import run_all
    click.echo(run_all(current_app._get_current_object(), force=True))
