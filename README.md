# HapiTech

Official website for **HapiTech**, an independent software development studio building modern websites, web applications and bespoke software solutions.

Designed, developed and maintained by HapiTech.

---

## Tech Stack

- **Backend:** Flask (Python)
- **Frontend:** HTML, CSS, JavaScript (Jinja2 Templates)
- **WSGI Server:** Gunicorn
- **Reverse Proxy:** NGINX
- **Process Management:** systemd
- **SSL:** Let's Encrypt

---

## Project Structure

```
hapitech/
├── app.py
├── wsgi.py
├── requirements.txt
├── templates/
├── static/
├── instance/
└── uploads/
```

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

---

## Deployment

The production application is served using **Gunicorn** behind **NGINX** with SSL provided by **Let's Encrypt**.

---

## Copyright

© HapiTech.

All rights reserved.

This project is proprietary software and may not be copied, modified, redistributed or reused without the express written permission of HapiTech.

[![Built by HapiTech](https://img.shields.io/badge/Built%20by-HapiTech-2563eb?style=for-the-badge)](https://hapitech.dev)