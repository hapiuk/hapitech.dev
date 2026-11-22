# routes/news.py — public AI news: latest strip, infinite-scroll feed, per-article pages.
# Every item is credited and linked to its publisher (see utils/news.py for what is shown).
import datetime

import click
from flask import Blueprint, abort, render_template, request

from utils.news import CATEGORIES, FEEDS, get_news, humanise_age, humanise_date, refresh

news_bp = Blueprint("news", __name__)

PAGE_SIZE = 10


@news_bp.app_template_filter("news_date")
def _news_date(iso):
    return humanise_date(iso)


def _filtered(cat):
    data = get_news()
    items = data.get("items", [])
    if cat in CATEGORIES:
        items = [i for i in items if i.get("cat") == cat]
    return data, items


def _cat():
    cat = request.args.get("cat", "all")
    return cat if cat in CATEGORIES else "all"


def _offset():
    try:
        return max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return 0


def _latest(items, n=6):
    """Newest items, at most two per source, for the strip along the top."""
    out, seen = [], {}
    for i in items:
        if seen.get(i["source_id"], 0) < 2:
            seen[i["source_id"]] = seen.get(i["source_id"], 0) + 1
            out.append(i)
        if len(out) == n:
            break
    return out


@news_bp.route("/news")
def news_page():
    cat, offset = _cat(), _offset()
    data, items = _filtered(cat)
    page = items[offset:offset + PAGE_SIZE]
    nxt = offset + PAGE_SIZE if offset + PAGE_SIZE < len(items) else None
    return render_template(
        "news.html",
        latest=_latest(data.get("items", [])) if offset == 0 else [],
        items=page,
        next_offset=nxt,
        cat=cat,
        categories=CATEGORIES,
        feeds=FEEDS,
        updated=humanise_age(data.get("fetched_at")),
        current_year=datetime.datetime.utcnow().year,
    )


@news_bp.route("/news/items")
def news_items():
    """HTML fragment for infinite scroll."""
    cat, offset = _cat(), _offset()
    _, items = _filtered(cat)
    page = items[offset:offset + PAGE_SIZE]
    nxt = offset + PAGE_SIZE if offset + PAGE_SIZE < len(items) else None
    resp = render_template("news/_items.html", items=page)
    return resp, 200, {"X-Next-Offset": "" if nxt is None else str(nxt), "Cache-Control": "no-store"}


@news_bp.route("/news/<item_id>")
def news_article(item_id):
    data = get_news()
    items = data.get("items", [])
    item = next((i for i in items if i.get("id") == item_id), None)
    if item is None:
        abort(404)
    more = [i for i in items if i.get("id") != item_id and i.get("cat") == item.get("cat")][:4]
    return render_template(
        "news/article.html",
        item=item,
        more=more,
        current_year=datetime.datetime.utcnow().year,
    )


@news_bp.cli.command("refresh")
def refresh_cmd():
    """Fetch all news feeds now (e.g. from cron: flask news refresh)."""
    data = refresh()
    click.echo(f"{len(data['items'])} items; errors: {data['errors'] or 'none'}")
