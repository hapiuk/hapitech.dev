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

	text_body = f"""Welcome to HapiTech Report!

Your tenant account for '{company_name}' has been provisioned.

ACCOUNT CREDENTIALS:
• Platform Login URL: {login_url}
• Company Name: {company_name}
• Admin Email: {recipient_email}
• Temporary Password: {temp_password}

HOW TO ACCESS YOUR ACCOUNT:
1. Visit {login_url}
2. Sign in with {recipient_email} and password: {temp_password}
3. Alternatively, click 'Sign in with email code' on the login page and enter {recipient_email}.

— HapiTech Report // Nostromo Division
"""

	html_body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{company_name} — Account Onboarding</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:Inter,system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#f1f5f9;">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0f172a;min-height:100vh;">
    <tr>
      <td align="center" valign="top" style="padding:40px 16px;">

        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;background:#1e293b;border:1px solid #334155;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.55);">
          <tr>
            <td style="padding:36px 36px 0 36px;">

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding-bottom:20px;">
                    <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#4db6ff;font-weight:600;">
                      HAPITECH REPORT // NOSTROMO DIVISION
                    </div>
                  </td>
                </tr>
              </table>

              <div style="height:1px;background:#334155;margin-bottom:24px;"></div>

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" style="padding-bottom:8px;">
                    <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;font-weight:600;">
                      TENANT ONBOARDING
                    </div>
                  </td>
                </tr>
                <tr>
                  <td align="center" style="padding-bottom:24px;">
                    <div style="font-size:22px;font-weight:700;color:#f8fafc;letter-spacing:-0.3px;">
                      {company_name}
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Credentials Tile -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:28px;">
                <tr>
                  <td style="background:#0f172a;border:1.5px solid #3b82f6;border-radius:12px;padding:20px 24px;">
                    <div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#60a5fa;font-weight:700;margin-bottom:12px;">
                      ACCOUNT CREDENTIALS
                    </div>
                    <div style="font-size:13px;line-height:1.8;color:#cbd5e1;">
                      <div><strong style="color:#94a3b8;">Company:</strong> <span style="color:#f8fafc;">{company_name}</span></div>
                      <div><strong style="color:#94a3b8;">Admin Email:</strong> <span style="color:#4db6ff;font-family:monospace;">{recipient_email}</span></div>
                      <div><strong style="color:#94a3b8;">Temp Password:</strong> <span style="color:#f8fafc;font-family:monospace;background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">{temp_password}</span></div>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Action Button -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:28px;">
                <tr>
                  <td align="center">
                    <a href="{login_url}" target="_blank" style="display:inline-block;background:#1d4ed8;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:14px 28px;border-radius:10px;box-shadow:0 4px 20px rgba(29,78,216,0.4);">
                      Log In to HapiTech Report ↗
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Instructions & Security -->
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="padding-bottom:20px;">
                    <p style="margin:0;font-size:13px;line-height:1.7;color:#94a3b8;">
                      You can log in with your Admin Email &amp; Temporary Password, or click <strong style="color:#f1f5f9;">"Sign in with email code"</strong> on the login screen to receive a 6-digit code.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding-bottom:24px;">
                    <div style="background:rgba(30,41,59,0.5);border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:12px 14px;">
                      <p style="margin:0;font-size:12px;line-height:1.6;color:#94a3b8;">
                        <strong style="color:#60a5fa;">Security Note:</strong> Please change your temporary password after your initial login from your profile settings.
                      </p>
                    </div>
                  </td>
                </tr>
              </table>

              <div style="height:1px;background:#334155;margin-bottom:20px;"></div>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:0 36px 24px 36px;">
              <div style="font-size:12px;color:#64748b;line-height:1.6;">
                <div>— HapiTech Report // Nostromo Division</div>
                <div style="font-size:11px;color:#475569;margin-top:2px;">
                  Sent automatically by HapiTech — do not reply.
                </div>
              </div>
            </td>
          </tr>

        </table>

      </td>
    </tr>
  </table>

</body>
</html>"""

	msg = EmailMessage()
	msg["Subject"] = f"Welcome to HapiTech Report — Onboarding for {company_name}"
	msg["From"] = mail_from
	msg["To"] = recipient_email
	msg.set_content(text_body)
	msg.add_alternative(html_body, subtype="html")

	with smtplib.SMTP(host, port, timeout=20) as s:
		s.ehlo()
		s.starttls()
		s.ehlo()
		s.login(user, password)
		s.send_message(msg)