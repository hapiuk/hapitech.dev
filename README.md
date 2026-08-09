# HapiTech

Official website for **HapiTech**, an independent software development studio building modern websites, web applications and bespoke software solutions.

This repo also hosts **Solar Journal** (`/solar-system`) — a public 3D solar-system explorer with body scanning, exploration points, and a personal/community journal. It's built as a self-contained module (own database bind, own auth, no foreign keys into the main site tables) so it can be split out later if needed.

Designed, developed and maintained by HapiTech.

---

## Tech Stack

- **Backend:** Flask (Python), SQLAlchemy + Alembic (Flask-Migrate), Flask-Login
- **Frontend:** HTML, CSS, JavaScript (Jinja2 templates); Solar Journal's 3D view is hand-rolled JS in `static/solar-system/`
- **Images:** Pillow (Solar Journal uploads)
- **Production:** Gunicorn behind NGINX, systemd, Let's Encrypt SSL

---

## Features

- **Public site** — homepage, contact form (SMTP), privacy policy and terms
- **Admin portal** — client CRUD, dashboard stats, internal ops tools (admin-only)
- **Client portal** — login-gated dashboard for clients
- **Solar Journal** — passwordless email one-time-code auth, 3D explorer, scanning / exploration points, per-body journal entries with image uploads

---

## Project Structure

```
hapitech/
├── app.py                 # App factory — main site, admin, client portal
├── manage.py              # Flask-Migrate entrypoint
├── models/                # SQLAlchemy models (main site + solar bind)
├── routes/                # Blueprints (solar system, journal API, admin tools)
├── utils/                 # Mailer, image limits, journal helpers, static body data
├── templates/             # Jinja2 templates
├── static/                # CSS/JS/media + solar-system 3D assets
├── migrations/            # Alembic migrations (main site models only)
├── instance/              # Local runtime data (gitignored)
├── requirements.txt
└── README.md
```

### Persistence (three separate stores)

| Store | Used for | How it's managed |
| --- | --- | --- |
| Default SQLAlchemy bind | Admin/client users and clients | Alembic (`flask db upgrade`) |
| `"solar"` SQLAlchemy bind | Solar Journal users, login codes, entries | `db.create_all` + startup column patches |
| Raw sqlite3 (via `utils/journal_db.py`) | Admin personal dev journal API | Created at startup; path overridable with `HAPITECH_DB_PATH` |

Database files and `instance/` are gitignored — never commit them.

---

## Local Development

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt

# Main-site tables (User / Client)
flask --app manage.py db upgrade

python app.py
```

App listens on `http://127.0.0.1:5000` (dev server binds `0.0.0.0:5000`).

### Environment variables

All optional for local use — the app falls back to SQLite and a **dev-only** secret key if unset. Set real values in production (via environment or a gitignored `.env`; `python-dotenv` is available).

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask session signing — **required in production** |
| `DATABASE_URL` | Main site DB (default: `sqlite:///hapitech.db`) |
| `SOLAR_DATABASE_URL` | Solar Journal DB (default: `sqlite:///solar_journal.db`) |
| `HAPITECH_DB_PATH` | Override path for the admin journal sqlite file |
| `SMTP_HOST` | SMTP server host |
| `SMTP_PORT` | SMTP port (default `587`) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASS` | SMTP password |
| `SMTP_FROM` | From address |
| `SMTP_TO` | Inbox for contact-form messages |

Without SMTP configured, the contact form and Solar Journal login-code emails will fail at send time.

**Do not commit** `.env`, database files, backups, or real credentials.

---

## Deployment

Production is intended to run under a WSGI server (e.g. Gunicorn) behind a reverse proxy with TLS. Exact unit names, paths and proxy config are environment-specific and intentionally not documented here.

For the main site schema:

```bash
flask --app manage.py db upgrade
```

---

## Security notes (public repo)

- No secrets, API keys, or production connection strings belong in this repository.
- Admin routes and ops tooling are login- and role-gated; treat production `SECRET_KEY`, SMTP credentials and host access as sensitive.
- Uploads and request bodies are size-capped in the app config.

If you find a vulnerability, please report it privately to HapiTech rather than opening a public issue with exploit detail.

---

## Copyright

© HapiTech.

All rights reserved.

This project is proprietary software and may not be copied, modified, redistributed or reused without the express written permission of HapiTech.

[![Built by HapiTech](https://img.shields.io/badge/Built%20by-HapiTech-2563eb?style=for-the-badge)](https://hapitech.dev)
