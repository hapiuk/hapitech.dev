# utils/links.py — absolute links for things that leave the site (texts, emails, QR codes).
import re
from urllib.parse import quote

from flask import current_app, request


def public_url(path: str) -> str:
    base = current_app.config.get("PUBLIC_BASE_URL") or request.url_root
    return base.rstrip("/") + "/" + path.lstrip("/")


def uk_to_intl(phone: str) -> str:
    """'07554 585833' / '+44 7554…' -> '447554585833' (for wa.me). Empty if it doesn't look like a number."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("0") and len(digits) == 11:
        digits = "44" + digits[1:]
    return digits if 10 <= len(digits) <= 15 else ""


def sms_href(phone: str, body: str) -> str:
    # "sms:<number>?&body=" works on both iOS and Android messaging apps
    num = re.sub(r"[^\d+]", "", phone or "")
    return f"sms:{num}?&body={quote(body)}"


def whatsapp_href(phone: str, body: str) -> str:
    intl = uk_to_intl(phone)
    return f"https://wa.me/{intl}?text={quote(body)}" if intl else f"https://wa.me/?text={quote(body)}"
