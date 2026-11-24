# utils/pay_links.py — one online "Pay now" link per business, shown on unpaid invoices (page + email).
# The business picks ONE provider in Settings and pastes their link. Where the provider supports it,
# the invoice amount is added to the link so the customer doesn't have to type it.
from urllib.parse import urlparse

PROVIDERS = {
    # key: (label, allowed hosts, how to add the amount (None = can't), example)
    # Only Revolut for now (the one we've tested end to end). Others are added on request: see Settings.
    "revolut": ("Revolut", ("revolut.me", "checkout.revolut.com", "pay.revolut.com"), None, "https://revolut.me/yourname"),
}


def clean(kind, url):
    """Returns (kind, url) to store, or raises ValueError with a friendly message. kind '' = no button."""
    kind = (kind or "").strip()
    url = (url or "").strip()
    if not kind or kind not in PROVIDERS:
        return None, None
    if not url:
        raise ValueError("Paste your payment link, or choose “No online payment”.")
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme != "https" or not p.netloc or " " in url:
        raise ValueError("That doesn't look like a web link. It should start with https://")
    hosts = PROVIDERS[kind][1]
    if hosts and p.netloc.lower() not in hosts:
        raise ValueError(f"That isn't a {PROVIDERS[kind][0]} link. It should look like {PROVIDERS[kind][3]}")
    return kind, url[:300]


def for_invoice(account, amount):
    """{'label', 'url', 'with_amount'} for this business's pay button, or None."""
    kind, url = getattr(account, "pay_link_kind", None), getattr(account, "pay_link", None)
    if not (kind in PROVIDERS and url):
        return None
    label, _, amount_fmt, _ = PROVIDERS[kind]
    with_amount = False
    if amount_fmt and amount and amount > 0 and not ("paypal.com" in url and "paypal.me" not in url):
        url = url.rstrip("/") + amount_fmt.format(n=f"{amount:.2f}")
        with_amount = True
    return {"label": label if kind != "other" else "online", "url": url, "with_amount": with_amount, "kind": kind}
