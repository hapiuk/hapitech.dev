# utils/updates.py — client update notes (docs/client-updates.md) turned into friendly emails.
# The file is plain Markdown: each "## " heading is one update. Supported: paragraphs, **bold**,
# "- " bullet lists, {name} (the client's first name), and "- (Roland)" / "- (Ray)" lines that only
# go to that client.
import html
import os
import re

from flask import current_app

FILE = "docs/client-updates.md"
INVITE_FILE = "docs/client-invite.md"
FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
BLUE = "#2563eb"


def _path(file=FILE):
    return os.path.join(current_app.root_path, file)


def sections(file=FILE) -> list[dict]:
    """[{"title", "body"}], newest first (as written in the file)."""
    try:
        raw = open(_path(file), encoding="utf-8").read()
    except OSError:
        return []
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    out = []
    for block in re.split(r"^## ", raw, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        out.append({"title": title.strip(), "body": body.strip()})
    return out


def owner_email(account):
    from models.core import User
    u = User.query.filter_by(account_id=account.id, role="owner").order_by(User.id).first()
    return (u.email if u else None) or account.contact_email


def _vars(account):
    """Placeholders: {name} {business} {plan_end} {charge_from} {price} {login_email}."""
    import datetime as dt
    from utils.plans import MONTHLY_PRICE, friends_end_default
    ad = account.addon()
    end = ad.trial_ends_at if ad and ad.status == "friends" and ad.trial_ends_at else friends_end_default()
    return {"{business}": account.name, "{plan_end}": f"{end:%-d %B %Y}",
            "{charge_from}": f"{end + dt.timedelta(days=1):%-d %B %Y}", "{price}": f"£{MONTHLY_PRICE}",
            "{login_email}": owner_email(account) or ""}


def _plan_html(v):
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 18px 0;'
            f'background:#eef4ff;border:1px solid #cfdcfb;border-radius:14px;"><tr><td style="padding:16px 18px;font:15px/1.55 {FONT};color:#16181d;">'
            f'<div style="font:700 12px/1 {FONT};letter-spacing:.08em;text-transform:uppercase;color:{BLUE};margin-bottom:8px;">🤝 Your Friends plan</div>'
            f'<div style="font:700 18px/1.3 {FONT};margin-bottom:6px;">Everything included, free until {v["{plan_end}"]}</div>'
            f'<div style="color:#4a4f59;">From {v["{charge_from}"]} it\'s <strong>{v["{price}"]} a month</strong>. No card needed now, and I\'ll remind you before then.</div>'
            f'</td></tr></table>')


def _login_html(v):
    from utils.links import public_url
    url = public_url("/login")
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 8px 0;background:#f7f6f3;'
            f'border-radius:12px;border:1px solid #ece9e3;"><tr><td style="padding:10px 14px;font:14px/1.4 {FONT};color:#7a7f89;white-space:nowrap;">Log in with</td>'
            f'<td style="padding:10px 14px;font:600 14px/1.4 {FONT};color:#16181d;">{html.escape(v["{login_email}"])}</td></tr></table>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:12px 0 18px 0;"><tr><td style="border-radius:999px;background:{BLUE};">'
            f'<a href="{url}" style="display:inline-block;padding:14px 26px;font:700 16px/1 {FONT};color:#ffffff;text-decoration:none;border-radius:999px;">'
            f'Open your dashboard</a></td></tr></table>')


def _for(account, body):
    """Keep lines for this client only, fill in their name."""
    who = (account.contact_name or account.name).split()[0]
    keep = []
    for line in body.splitlines():
        m = re.match(r"^(\s*-\s*)\((\w+)\)\s*(.*)$", line)
        if m:
            if m.group(2).lower() != who.lower():
                continue
            line = m.group(1) + m.group(3)
        keep.append(line)
    out = "\n".join(keep).replace("{name}", who)
    if "{" in out:
        for k, v in _vars(account).items():
            out = out.replace(k, v)
    return out


def _inline(s):
    s = html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


P = "margin:0 0 14px 0;"
H = "margin:22px 0 8px 0;font:700 17px/1.3 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#16181d;"
UL = "margin:0 0 16px 0;padding:0 0 0 20px;"
LI = "margin:0 0 8px 0;"


def render(account, section) -> tuple[str, str]:
    """(text, html_block) for one update, personalised for this client. Goes line by line:
    "- " lines are bullets, a line that is only **bold** is a sub-heading, blank lines end a paragraph."""
    text_parts, html_parts, para, bullets = [], [], [], []

    def end_para():
        if para:
            html_parts.append(f'<p style="{P}">' + "<br>".join(_inline(l) for l in para) + "</p>")
            text_parts.append("\n".join(l.replace("**", "") for l in para))
            para.clear()

    def end_list():
        if bullets:
            html_parts.append(f'<ul style="{UL}">' + "".join(f'<li style="{LI}">{_inline(x)}</li>' for x in bullets) + "</ul>")
            text_parts.append("\n".join(f"• {x.replace('**', '')}" for x in bullets))
            bullets.clear()

    v = None
    for raw in _for(account, section["body"]).splitlines():
        line = raw.strip()
        if line in ("[[plan]]", "[[login]]"):
            end_para(); end_list()
            v = v or _vars(account)
            if line == "[[plan]]":
                html_parts.append(_plan_html(v))
                text_parts.append(f"YOUR FRIENDS PLAN: everything included, free until {v['{plan_end}']}. "
                                  f"From {v['{charge_from}']} it's {v['{price}']} a month.")
            else:
                from utils.links import public_url
                html_parts.append(_login_html(v))
                text_parts.append(f"Log in with: {v['{login_email}']}\nOpen your dashboard: {public_url('/login')}")
            continue
        if not line:
            end_para(); end_list()
        elif line.startswith("- "):
            end_para(); bullets.append(line[2:])
        elif re.fullmatch(r"\*\*[^*]+\*\*", line):
            end_para(); end_list()
            html_parts.append(f'<h2 style="{H}">{html.escape(line[2:-2])}</h2>')
            text_parts.append(line[2:-2].upper())
        else:
            end_list(); para.append(line)
    end_para(); end_list()
    return "\n\n".join(text_parts), "".join(html_parts)


def page(account, section, preheader=None):
    """(text, full html email) exactly as it will be sent."""
    from utils import email_html
    text, block = render(account, section)
    _, html_page = email_html.build(section["title"], html_block=block,
                                    preheader=preheader or section.get("preheader") or text.split("\n")[0][:120])
    return text, html_page


def send(account, section, to=None, preheader=None):
    from utils.mailer import send_email
    text, html_page = page(account, section, preheader)
    send_email(to=to or owner_email(account), subject=section["title"], text=text, html=html_page,
               reply_to="aaron@hapitech.dev", from_name="Aaron at HapiTech")
