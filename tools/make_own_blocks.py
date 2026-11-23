"""tools/make_own_blocks.py — make HapiTech's own sites (hapitech.dev, hapitech.report) editable in My website.

Finds the headings and paragraphs on each homepage, wraps each one as
    {% if ed('key') %}{{ ed('key') | richtext }}{% else %}…original…{% endif %}
so the page looks exactly the same until something is edited, and writes the list (site order) to
utils/site_blocks/<domain>.json. Safe to run again: already-wrapped text is left alone.

    python tools/make_own_blocks.py            # dry run: list what would become editable
    python tools/make_own_blocks.py --write
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITES = [
    ("hapitech.dev", "templates/home.html", {
        "hero": "Top of page", "services": "Services", "ai": "AI", "work": "Our work", "process": "How it works",
        "about": "About", "updates": "Updates", "reviews": "Reviews", "news": "AI news", "contact": "Get in touch", "strip": "Sites we look after"}),
    ("hapitech.report", "templates/hub/home.html", {
        "hb-hero": "Top of page", "how": "How it works", "sources": "Where reviews come from", "businesses": "Businesses",
        "latest": "Latest reviews", "offer": "For businesses"}),
]
TAG = re.compile(r'<(h1|h2|h3|p)((?:\s+[a-z-]+="[^"]*")*)\s*>(.*?)</\1>', re.S)
SECTION = re.compile(r'<section\b([^>]*)>')
SKIP_CLASSES = ("kicker", "shot__", "upd__", "news-card", "hb-muted", "small", "hb-ad", "hb-step__n")


def plain(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in s.split("\n")).strip()


def run(domain, path, names, write):
    p = os.path.join(ROOT, path)
    src = open(p, encoding="utf-8").read()
    sections = [(m.start(), m.group(1)) for m in SECTION.finditer(src)]

    def group_at(pos):
        attrs = ""
        for start, a in sections:
            if start < pos:
                attrs = a
        m = re.search(r'id="([^"]+)"', attrs) or re.search(r'class="([^" ]+)', attrs)
        key = m.group(1) if m else "page"
        return key, names.get(key, key.replace("-", " ").title())

    defs, counts, out, last = [], {}, [], 0
    for m in TAG.finditer(src):
        tag, attrs, inner = m.group(1), m.group(2) or "", m.group(3)
        if "{" in inner or "ed('" in inner or any(c in attrs for c in SKIP_CLASSES) or "class=\"shot" in src[max(0, m.start() - 120):m.start()]:
            continue
        text = plain(inner)
        if len(text) < 3 or "<a " in inner or (tag == "p" and len(text) < 25):
            continue                    # tiny labels, and text with links in it, stay as they are
        gkey, gname = group_at(m.start())
        kind = "heading" if tag in ("h1", "h2") else "title" if tag == "h3" else "text"
        counts[(gkey, kind)] = counts.get((gkey, kind), 0) + 1
        key = f"{gkey}.{kind}{counts[(gkey, kind)]}"
        long = tag == "p" or len(text) > 70
        defs.append({"key": key, "type": "longtext" if long else "text", "group": gname,
                     "label": f"{gname}: {kind} · “{text[:40]}{'…' if len(text) > 40 else ''}”",
                     "default": text, "max_length": max(60, min(600, int(len(text) * 1.6) + 20)), "sort": len(defs)})
        out.append(src[last:m.start()])
        out.append(f"<{tag}{attrs}>{{% if ed('{key}') %}}{{{{ ed('{key}') | richtext }}}}{{% else %}}{inner}{{% endif %}}</{tag}>")
        last = m.end()
    out.append(src[last:])
    for d in defs:
        print(f"  {d['key']:22} {d['type']:8} {d['default'][:70]!r}")
    print(f"{domain}: {len(defs)} editable sections")
    if write and defs:
        open(p, "w", encoding="utf-8").write("".join(out))
        json.dump(defs, open(os.path.join(ROOT, "utils/site_blocks", f"{domain}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    for d, path, names in SITES:
        run(d, path, names, "--write" in sys.argv)
