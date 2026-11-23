# utils/email_html.py — turns an email's content into the shared HTML design (templates/email/base.html)
# plus a matching plain-text version. Client emails use the client's logo + colour; system emails HapiTech's.
from flask import current_app, render_template, url_for
from markupsafe import Markup

from utils.links import public_url

HAPITECH = {"name": "HapiTech", "logo_path": "media/favicon/apple-touch-icon.png", "colour": "#2563eb",
            "site": "https://hapitech.dev", "site_label": "hapitech.dev"}


def _on_colour(hex_colour):
    """White or near-black text, whichever reads better on the brand colour."""
    h = (hex_colour or "#2563eb").lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"
    return "#16181d" if (0.299 * r + 0.587 * g + 0.114 * b) > 170 else "#ffffff"


def brand(account=None):
    if account is None:
        b = dict(HAPITECH)
    else:
        b = {"name": account.name, "logo_path": account.logo_path, "colour": account.brand_colour or "#2563eb",
             "site": f"https://{account.domain}" if account.domain else None, "site_label": account.domain}
    b["logo"] = public_url(url_for("static", filename=b["logo_path"])) if b.get("logo_path") else None
    b["on_colour"] = _on_colour(b["colour"])
    return b


def build(subject, *, account=None, heading=None, lines=(), code=None, box=None, button=None, after=(),
          sign=None, footer=None, html_block=None, preheader=None):
    """Returns (text, html) for send_email(text=..., html=...)."""
    b = brand(account)
    html = render_template("email/base.html", subject=subject, brand=b, heading=heading, lines=list(lines), code=code,
                           box=box, button=button, after=list(after), sign=sign, footer=footer,
                           html_block=Markup(html_block) if html_block else None,
                           preheader=preheader or (lines[0] if lines else heading or subject))
    parts = [heading] if heading else []
    parts += list(lines)
    if code:
        parts.append(code)
    if box:
        parts.append("\n".join(f"{k}: {v}" for k, v in box))
    if button:
        parts.append(f"{button['label']}: {button['url']}")
    parts += list(after)
    if sign:
        parts.append(sign)
    if footer:
        parts.append(footer)
    text = "\n\n".join(str(p) for p in parts if p)
    return text, html


def send(to, subject, *, reply_to=None, from_name=None, **content):
    from utils.mailer import send_email
    text, html = build(subject, **content)
    send_email(to=to, subject=subject, text=text, html=html, reply_to=reply_to, from_name=from_name)
