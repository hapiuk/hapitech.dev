import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


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


def send_login_code_email(*, email: str, code: str) -> None:
	host = os.getenv("SMTP_HOST")
	port = int(os.getenv("SMTP_PORT", "587"))
	user = os.getenv("SMTP_USER")
	password = os.getenv("SMTP_PASS")
	mail_from = os.getenv("SMTP_FROM", user or "")

	if not all([host, port, user, password, mail_from]):
		raise RuntimeError("SMTP env vars missing (SMTP_HOST/PORT/USER/PASS/FROM)")

	msg = EmailMessage()
	msg["Subject"] = f"Your Solar Journal code: {code}"
	msg["From"] = mail_from
	msg["To"] = email
	msg.set_content(
		f"Your one-time Solar Journal login code is:\n\n"
		f"    {code}\n\n"
		f"This code expires in 10 minutes. If you didn't request this, you can ignore this email.\n"
	)

	with smtplib.SMTP(host, port, timeout=20) as s:
		s.ehlo()
		s.starttls()
		s.ehlo()
		s.login(user, password)
		s.send_message(msg)


def send_onboarding_email(*, recipient_email: str, company_name: str, temp_password: str, login_url: str) -> None:
	host = os.getenv("SMTP_HOST")
	port = int(os.getenv("SMTP_PORT", "587"))
	user = os.getenv("SMTP_USER")
	password = os.getenv("SMTP_PASS")
	mail_from = os.getenv("SMTP_FROM", user or "")

	if not all([host, port, user, password, mail_from]):
		raise RuntimeError("SMTP env vars missing (SMTP_HOST/PORT/USER/PASS/FROM)")

	msg = EmailMessage()
	msg["Subject"] = f"Welcome to HapiTech Report — Onboarding for {company_name}"
	msg["From"] = mail_from
	msg["To"] = recipient_email
	msg.set_content(
		f"Welcome to HapiTech Report!\n\n"
		f"Your tenant account for '{company_name}' has been provisioned.\n\n"
		f"ACCOUNT CREDENTIALS:\n"
		f"• Login URL: {login_url}\n"
		f"• Company: {company_name}\n"
		f"• Admin Email: {recipient_email}\n"
		f"• Temporary Password: {temp_password}\n\n"
		f"HOW TO ACCESS:\n"
		f"1. Open {login_url}\n"
		f"2. Sign in with {recipient_email} and password: {temp_password}\n"
		f"3. Or click 'Sign in with email code' on the login page and enter {recipient_email}.\n"
	)

	with smtplib.SMTP(host, port, timeout=20) as s:
		s.ehlo()
		s.starttls()
		s.ehlo()
		s.login(user, password)
		s.send_message(msg)