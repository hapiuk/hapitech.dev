# utils/updates.py — client update notes (docs/client-updates.md) turned into friendly emails.
# The file is plain Markdown: each "## " heading is one update. Supported: paragraphs, **bold**,
# "- " bullet lists, {name} (the client's first name), and "- (Roland)" / "- (Ray)" lines that only
# go to that client.
import html
import os
import re

from flask import current_app

FILE = "docs/client-updates.md"


def _path():
    return os.path.join(current_app.root_path, FILE)


def sections() -> list[dict]:
    """[{"title", "body"}], newest first (as written in the file)."""
    try:
        raw = open(_path(), encoding="utf-8").read()
    except OSError:
        return []
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    out = []
    for block in re.split(r"^## ", raw, flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        out.append({"title": title.strip(), "body": body.strip()})
    return out


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
    return "\n".join(keep).replace("{name}", who)


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

    for raw in _for(account, section["body"]).splitlines():
        line = raw.strip()
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


def send(account, section, to=None):
    from utils import email_html
    from utils.mailer import send_email
    text, block = render(account, section)
    _, page = email_html.build(section["title"], html_block=block, preheader=text.split("\n")[0][:120])
    send_email(to=to or account.contact_email, subject=section["title"], text=text, html=page,
               reply_to="aaron@hapitech.dev", from_name="Aaron at HapiTech")
