# utils/news.py
"""AI news aggregator for the public /news page.

Pulls headlines from publishers' public RSS/Atom feeds and always credits and links
the source. When a publisher puts the full article in its own feed (e.g. Simon
Willison, Ollama release notes) it is shown, sanitised, like a feed reader would.
Otherwise we show a link preview (the page's own og:image / og:description) and
send readers to the original. Article pages are never scraped for their full text.

Cache: a JSON file in the Flask instance folder, shared by all workers.
- get_news() never blocks on the network once a cache exists; a stale cache is
  served while a background thread refreshes it.
- First-ever call (no cache) fetches synchronously, unless blocking=False.
- `flask news-refresh` refreshes on demand (handy from cron).
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import html
import json
import os
import re
import threading
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

CACHE_TTL_SECONDS = 60 * 60          # refresh at most hourly
FETCH_TIMEOUT = 8                    # seconds per feed
ITEMS_PER_FEED = 30
EXCERPT_CHARS = 260
FULL_CONTENT_MIN_CHARS = 600         # feed text longer than this is shown as the article
MAX_ITEMS_KEPT = 500                 # history kept across refreshes (for infinite scroll)
MAX_AGE_DAYS = 120
PREVIEW_FETCHES_PER_REFRESH = 40     # og:image / og:description lookups per refresh
USER_AGENT = "HapiTechNews/1.0 (+https://hapitech.dev/news)"

CATEGORIES = {
    "local": "Local & open models",
    "frontier": "Frontier labs",
}

# Only sources with a working public feed. Anthropic has no official RSS feed.
FEEDS = [
    {"id": "huggingface", "name": "Hugging Face", "home": "https://huggingface.co/blog",
     "url": "https://huggingface.co/blog/feed.xml", "cat": "local"},
    {"id": "willison", "name": "Simon Willison", "home": "https://simonwillison.net/tags/local-llms/",
     "url": "https://simonwillison.net/tags/local-llms.atom", "cat": "local"},
    {"id": "ollama", "name": "Ollama releases", "home": "https://github.com/ollama/ollama/releases",
     "url": "https://github.com/ollama/ollama/releases.atom", "cat": "local"},
    {"id": "openai", "name": "OpenAI", "home": "https://openai.com/news/",
     "url": "https://openai.com/news/rss.xml", "cat": "frontier"},
    {"id": "deepmind", "name": "Google DeepMind", "home": "https://deepmind.google/discover/blog/",
     "url": "https://deepmind.google/blog/rss.xml", "cat": "frontier"},
    {"id": "googleai", "name": "Google AI", "home": "https://blog.google/technology/ai/",
     "url": "https://blog.google/technology/ai/rss/", "cat": "frontier"},
]

_ATOM = "{http://www.w3.org/2005/Atom}"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
_MEDIA = "{http://search.yahoo.com/mrss/}"
_lock = threading.Lock()
_refreshing = False


# ---------------------------------------------------------------- sanitiser

class _Sanitiser(HTMLParser):
    """Allowlist HTML sanitiser: safe formatting tags only, http(s) links, https images."""
    ALLOWED = {"p", "br", "a", "strong", "b", "em", "i", "ul", "ol", "li", "blockquote",
               "pre", "code", "h3", "h4", "img", "figure", "figcaption", "hr", "sup", "sub"}
    RENAME = {"h1": "h3", "h2": "h3", "h5": "h4", "h6": "h4"}
    DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "svg", "form",
                         "noscript", "template", "button", "input", "select", "textarea", "video", "audio"}
    VOID = {"br", "img", "hr"}

    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.stack, self.skip = base, [], [], 0

    def _url(self, raw, https_only=False):
        u = urljoin(self.base, (raw or "").strip())
        ok = u.startswith("https://") or (not https_only and u.startswith("http://"))
        return html.escape(u, quote=True) if ok else ""

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip:
            return
        tag = self.RENAME.get(tag, tag)
        if tag not in self.ALLOWED:
            return
        a = dict(attrs)
        if tag == "a":
            href = self._url(a.get("href"))
            if not href:
                self.stack.append(None)          # keep the text, drop the link
                return
            self.out.append(f'<a href="{href}" target="_blank" rel="noopener nofollow ugc">')
        elif tag == "img":
            src = self._url(a.get("src"), https_only=True)
            if src:
                alt = html.escape(a.get("alt") or "", quote=True)
                self.out.append(f'<img src="{src}" alt="{alt}" loading="lazy" referrerpolicy="no-referrer">')
            return
        else:
            self.out.append(f"<{tag}>")
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        tag = self.RENAME.get(tag, tag)
        if tag not in self.ALLOWED or tag in self.VOID:
            return
        # close the most recent matching open tag (and anything left open inside it)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag or (tag == "a" and self.stack[i] is None):
                for t in reversed(self.stack[i:]):
                    if t:
                        self.out.append(f"</{t}>")
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def result(self):
        for t in reversed(self.stack):
            if t:
                self.out.append(f"</{t}>")
        return "".join(self.out).strip()


def sanitise(raw: str, base: str) -> str:
    p = _Sanitiser(base)
    try:
        p.feed(raw or "")
        p.close()
    except Exception:
        return ""
    return p.result()


def _item_id(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- parsing

def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _clean(raw: str, limit: int = EXCERPT_CHARS) -> str:
    """HTML → short plain-text excerpt cut on a word boundary."""
    s = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape(raw or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",.;:-–— ")
    return cut + "…"


def _date(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _safe_link(url: str) -> str:
    url = (url or "").strip()
    return url if url.startswith(("https://", "http://")) else ""


def _parse(xml_bytes: bytes, feed: dict) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    entries = []   # (title, link, body_html, date, image)
    if root.tag == f"{_ATOM}feed":
        for e in root.findall(f"{_ATOM}entry"):
            link = ""
            for l in e.findall(f"{_ATOM}link"):
                if l.get("rel", "alternate") == "alternate":
                    link = l.get("href", "")
                    break
            body = _text(e.find(f"{_ATOM}content")) or _text(e.find(f"{_ATOM}summary"))
            date = _text(e.find(f"{_ATOM}published")) or _text(e.find(f"{_ATOM}updated"))
            entries.append((_text(e.find(f"{_ATOM}title")), link, body, date, ""))
    else:
        for i in root.iter("item"):
            body = _text(i.find(_CONTENT)) or _text(i.find("description"))
            image = ""
            m = i.find(f"{_MEDIA}content")
            if m is None:
                m = i.find(f"{_MEDIA}thumbnail")
            if m is not None:
                image = m.get("url", "")
            enc = i.find("enclosure")
            if not image and enc is not None and (enc.get("type") or "").startswith("image/"):
                image = enc.get("url", "")
            entries.append((_text(i.find("title")), _text(i.find("link")), body, _text(i.find("pubDate")), image))

    out = []
    for title, link, body, date, image in entries:
        title, link, d = _clean(title, 160), _safe_link(link), _date(date)
        if not (title and link):
            continue
        if feed["id"] == "ollama":
            # release notes: skip release candidates, keep it to real versions
            if re.search(r"-rc|rc\d|pre", title, re.I):
                continue
            title = f"Ollama {title}" if not title.lower().startswith("ollama") else title
        plain = _clean(body, 10_000)
        content = sanitise(body, link) if len(plain) >= FULL_CONTENT_MIN_CHARS else ""
        out.append({
            "id": _item_id(link),
            "title": title,
            "link": link,
            "excerpt": _clean(body),
            "content": content,
            "image": image if image.startswith("https://") else "",
            "date": d.isoformat() if d else None,
            "source": feed["name"],
            "source_id": feed["id"],
            "source_home": feed["home"],
            "cat": feed["cat"],
        })
        if len(out) >= ITEMS_PER_FEED:
            break
    return out


_META_RE = re.compile(r"<meta\s[^>]*>", re.I)
_ATTR_RE = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


def _preview(item: dict) -> dict:
    """Link-preview data from the article page's own <meta> tags (no body text is taken)."""
    req = urllib.request.Request(item["link"], headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        head = _read(r, 600_000).decode("utf-8", "replace")
    head = head.split("</head>", 1)[0]
    meta = {}
    for tag in _META_RE.findall(head):
        attrs = {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in _ATTR_RE.finditer(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs and key not in meta:
            meta[key] = html.unescape(attrs["content"])
    img = urljoin(item["link"], meta.get("og:image") or meta.get("twitter:image") or "")
    desc = meta.get("og:description") or meta.get("description") or meta.get("twitter:description") or ""
    return {"image": img if img.startswith("https://") else "", "excerpt": _clean(desc)}


def _read(resp, limit: int) -> bytes:
    """Read a capped body; some CDNs send gzip even when it wasn't requested."""
    data = resp.read(limit)
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)[: limit * 4]
        except (OSError, EOFError):
            pass
    return data


def _fetch(feed: dict):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": USER_AGENT,
                                                       "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        data = _read(r, 3_000_000)        # hard cap: 3 MB per feed
    return _parse(data, feed)


# ---------------------------------------------------------------- cache

def _cache_path() -> str:
    try:
        from flask import current_app
        base = current_app.instance_path
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "news_cache.json")


def _load() -> dict | None:
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def refresh(path: str | None = None) -> dict:
    """Fetch every feed in parallel and merge into the kept history.
    A feed that fails simply contributes nothing new this round."""
    path = path or _cache_path()
    old = {}
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        pass
    by_id = {}
    for it in old.get("items", []):
        if it.get("link"):
            it.setdefault("id", _item_id(it["link"]))
            by_id[it["id"]] = it

    errors = {}
    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        futures = {f["id"]: pool.submit(_fetch, f) for f in FEEDS}
        for fid, fut in futures.items():
            try:
                for it in fut.result():
                    prev = by_id.get(it["id"], {})
                    if prev.get("previewed"):          # keep previously fetched preview data
                        it["previewed"] = True
                        it["image"] = it["image"] or prev.get("image", "")
                        it["excerpt"] = it["excerpt"] or prev.get("excerpt", "")
                    by_id[it["id"]] = it
            except Exception as exc:          # network, HTTP, XML: keep what we had
                errors[fid] = type(exc).__name__

    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_AGE_DAYS)).isoformat()
    items = [i for i in by_id.values() if (i.get("date") or "") >= cutoff]
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    items = items[:MAX_ITEMS_KEPT]

    # link previews for the newest items that have no image or text of their own
    todo = [i for i in items if not i.get("previewed") and not i.get("content")
            and not (i.get("image") and i.get("excerpt"))][:PREVIEW_FETCHES_PER_REFRESH]
    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for it, fut in [(i, pool.submit(_preview, i)) for i in todo]:
                try:
                    p = fut.result()
                    it["image"] = it.get("image") or p["image"]
                    it["excerpt"] = it.get("excerpt") or p["excerpt"]
                except Exception:
                    pass
                it["previewed"] = True

    data = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "items": items,
        "errors": errors,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)                    # atomic for other workers
    return data


def _age_seconds(data: dict) -> float:
    try:
        t = dt.datetime.fromisoformat(data["fetched_at"])
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()
    except (KeyError, ValueError, TypeError):
        return float("inf")


def _refresh_in_background(path: str):
    global _refreshing
    with _lock:
        if _refreshing:
            return
        _refreshing = True

    def run():
        global _refreshing
        try:
            refresh(path)
        except Exception as exc:
            print(f"[NEWS_REFRESH_ERROR] {exc}")
        finally:
            _refreshing = False

    threading.Thread(target=run, daemon=True).start()


def get_news(blocking: bool = True) -> dict:
    """Return {"fetched_at", "items", "errors"}; never raises."""
    path = _cache_path()
    data = _load()
    if data is None:
        if not blocking:
            _refresh_in_background(path)
            return {"fetched_at": None, "items": [], "errors": {}}
        try:
            return refresh(path)
        except Exception as exc:
            print(f"[NEWS_REFRESH_ERROR] {exc}")
            return {"fetched_at": None, "items": [], "errors": {}}
    if _age_seconds(data) > CACHE_TTL_SECONDS:
        _refresh_in_background(path)
    return data


# ---------------------------------------------------------------- template helpers

def humanise_date(iso: str | None) -> str:
    d = _date(iso or "")
    if not d:
        return ""
    days = (dt.datetime.now(dt.timezone.utc).date() - d.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return f"{d.day} {d.strftime('%b %Y')}"


def humanise_age(iso: str | None) -> str:
    d = _date(iso or "")
    if not d:
        return ""
    mins = int((dt.datetime.now(dt.timezone.utc) - d).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    hrs = mins // 60
    return f"{hrs} hour{'s' if hrs != 1 else ''} ago" if hrs < 48 else f"{hrs // 24} days ago"
