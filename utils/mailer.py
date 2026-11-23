# utils/mailer.py — all outgoing email.
# MAIL_MODE=smtp sends for real (SMTP_* env vars). MAIL_MODE=log (the default in development)
# writes each message to <instance>/mail_outbox/ instead, so local testing never emails anyone.
import datetime as dt
import os
import re
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def _mode():
    try:
        from flask import current_app
        return current_app.config.get("MAIL_MODE", "smtp")
    except RuntimeError:
        return os.getenv("MAIL_MODE", "smtp")


def _outbox_dir():
    try:
        from flask import current_app
        base = current_app.instance_path
    except RuntimeError:
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance")
    path = os.path.join(base, "mail_outbox")
    os.makedirs(path, exist_ok=True)
    return path


def send_email(*, to: str, subject: str, text: str, html: str | None = None,
               reply_to: str | None = None, from_name: str | None = None) -> None:
    """Send one email. Raises on SMTP failure so callers can report it."""
    user = os.getenv("SMTP_USER")
    mail_from = os.getenv("SMTP_FROM", user or "noreply@hapitech.dev")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{mail_from}>" if from_name else mail_from
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    if _mode() == "log":
        stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        safe_to = re.sub(r"[^a-zA-Z0-9@._-]", "_", to)[:60]
        with open(os.path.join(_outbox_dir(), f"{stamp}-{safe_to}.eml"), "w", encoding="utf-8") as f:
            f.write(msg.as_string())
        print(f"[MAIL:log] to={to} subject={subject!r}")
        return

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    password = os.getenv("SMTP_PASS")
    if not all([host, user, password, mail_from]):
        raise RuntimeError("SMTP env vars missing (SMTP_HOST/PORT/USER/PASS/FROM)")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)


def send_contact_email(*, name: str, email: str, message: str, meta: dict) -> None:
    """Website quote/contact form → Aaron's inbox."""
    to = os.getenv("SMTP_TO", os.getenv("SMTP_USER", "aaron@hapitech.dev"))
    subject = " • ".join(s for s in ["HapiTech Contact", meta.get("host") or "", meta.get("client") or ""] if s)
    body = (
        f"New contact form submission\n\n"
        f"Name: {name}\nEmail: {email}\n"
        f"Client: {meta.get('client', '')}\nHost: {meta.get('host', '')}\n"
        f"IP: {meta.get('ip', '')}\nUser-Agent: {meta.get('ua', '')}\n"
        f"Referer: {meta.get('referer', '')}\nTime (UTC): {meta.get('utc', '')}\n\n"
        f"Message:\n{message}\n"
    )
    html = None
    try:
        from utils import email_html
        _, html = email_html.build(subject, heading="New enquiry from hapitech.dev",
                                   lines=[f"{name} sent a message through the website."],
                                   box=[("Name", name), ("Email", email), ("Form", meta.get("client", "") or "—")],
                                   after=[message], footer="Reply to this email to answer them directly.")
    except Exception as exc:          # never lose an enquiry over styling
        print(f"[CONTACT_HTML] {exc}")
    send_email(to=to, subject=subject, text=body, html=html, reply_to=email)
