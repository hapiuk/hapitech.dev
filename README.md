# HapiTech

Official website for **HapiTech**, an independent software development studio building modern websites, web applications and bespoke software solutions.

This repo also currently hosts **Solar Journal**, a public 3D solar-system explorer with gamified body-scanning and a personal/community journal. It's built as a self-contained module — its own database bind, its own auth system, no foreign keys into the HapiTech tables — deliberately so it can be split out into its own deployment.

Designed, developed and maintained by HapiTech.

---

## Tech Stack

- **Backend:** Flask (Python), SQLAlchemy + Alembic (Flask-Migrate)
- **Frontend:** HTML, CSS, JavaScript (Jinja2 templates); Solar Journal's 3D view is hand-rolled JS in `static/solar-system/`
- **WSGI Server:** Gunicorn
- **Reverse Proxy:** NGINX
- **Process Management:** systemd
- **SSL:** Let's Encrypt

---

## Project Structure

```
hapitech/
├── app.py                # app factory — main site, admin, client portal
├── manage.py              # Flask-Migrate shell entrypoint
├── models/                # SQLAlchemy models
├── routes/                # blueprints: solar_system, journal_api, admin_command_center
├── utils/                 # mailer, image processing, service ops, curated body facts
├── templates/              # Jinja2 templates (site, admin, solar system)
├── static/                 # CSS/JS/media + solar-system 3D assets/textures
├── migrations/              # Alembic migrations (main site models only)
├── instance/                # auto-created by Flask-SQLAlchemy — holds solar_journal.db
├── requirements.txt
└── README.md
```

### Key subsystems

- **HapiTech site & client portal** — homepage, contact form (SMTP), admin/client login, client CRUD, and an admin **command center** that runs whitelisted `systemctl`/`journalctl` commands against HapiTech's own service and three client deployments (`spartanbricklaying`, `rolandshandyman`, `gravemistakegames`).
- **Solar Journal** (`/solar-system`) — public, passwordless auth (emailed one-time code), 3D solar system explorer, exploration-point scanning, per-body journal entries with image uploads. Own SQLAlchemy bind (`"solar"`) → `instance/solar_journal.db`.
- **Personal dev journal** (`/api/journal/*`) — admin-only project log (entries + goals), backed by a separate raw sqlite3 file (`utils/hapitech.sqlite3`), unrelated to Solar Journal.

---

## Local Development

```bash
python -m venv venv

# Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt

python app.py
```

Optional environment variables — the app runs with safe local defaults (SQLite, dev secret key) if these aren't set:

- `SECRET_KEY`, `DATABASE_URL`, `SOLAR_DATABASE_URL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO` — required for the contact form and Solar Journal login-code emails to actually send

---

## Deployment

The production application is served using **Gunicorn** behind **NGINX** with SSL provided by **Let's Encrypt**.

---

## Copyright

© HapiTech.

All rights reserved.

This project is proprietary software and may not be copied, modified, redistributed or reused without the express written permission of HapiTech.

[![Built by HapiTech](https://img.shields.io/badge/Built%20by-HapiTech-2563eb?style=for-the-badge)](https://hapitech.dev)