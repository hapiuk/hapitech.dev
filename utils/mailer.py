import os
import smtplib
from email.message import EmailMessage


def send_contact_email(*, name: str, email: str, message: str, meta: dict) -> None:
	host = os.getenv("SMTP_HOST")
	port = int(os.getenv("SMTP_PORT", "587"))
	user = os.getenv("SMTP_USER")
	password = os.getenv("SMTP_PASS")
	mail_from = os.getenv("SMTP_FROM", user or "")
	mail_to = os.getenv("SMTP_TO", user or "")

	if not all([host, port, user, password, mail_from, mail_to]):
		raise RuntimeError("SMTP env vars missing (SMTP_HOST/PORT/USER/PASS/FROM/TO)")

	subject_bits = [
		"HapiTech Contact",
		meta.get("host") or "",
		meta.get("client") or "",
	]
	subject = " • ".join([s for s in subject_bits if s]).strip()

	body = (
		f"New contact form submission\n\n"
		f"Name: {name}\n"
		f"Email: {email}\n"
		f"Client: {meta.get('client','')}\n"
		f"Host: {meta.get('host','')}\n"
		f"IP: {meta.get('ip','')}\n"
		f"User-Agent: {meta.get('ua','')}\n"
		f"Referer: {meta.get('referer','')}\n"
		f"Time (UTC): {meta.get('utc','')}\n\n"
		f"Message:\n{message}\n"
	)

	msg = EmailMessage()
	msg["Subject"] = subject
	msg["From"] = mail_from
	msg["To"] = mail_to
	msg["Reply-To"] = email
	msg.set_content(body)

	with smtplib.SMTP(host, port, timeout=20) as s:
		s.ehlo()
		s.starttls()
		s.ehlo()
		s.login(user, password)
		s.send_message(msg)
