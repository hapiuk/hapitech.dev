# utils/plan_value.py — a client's transaction history with HapiTech, for their "My plan" page, receipts, and the
# admin Money tab (pricing reference).
#   * work done (jobs) is charged on its date;
#   * each running cost is charged on every renewal date from its start (monthly / quarterly / yearly / once);
#   * anything "covered" gets a matching Friends plan deduction on the same transaction;
#   * payments land on the transaction with the same date.
# Everything on one date is one transaction (one receipt). The next 31 days show as "upcoming".
import datetime as dt

DONATE_KEY = "donate_url"          # (old single link, no longer used)
SUPPORT_KEYS = ("support_paypal", "support_revolut")
UPCOMING_DAYS = 31


def _ref(account, d):
    return f"HT-{account.id:03d}-{d:%Y%m%d}"


def transactions(account, today=None):
    today = today or dt.date.today()
    ad = account.addon()
    deduction = "Friends plan" if ad and ad.status == "friends" else "Covered by HapiTech"
    groups = {}

    def group(d):
        return groups.setdefault(d, {"date": d, "ref": _ref(account, d), "lines": [], "deductions": [], "payments": []})

    for j in account.jobs:
        if j.status == "done" and float(j.price_gbp or 0) > 0 and j.due_date:
            group(j.due_date)["lines"].append({"title": j.title, "amount": float(j.price_gbp), "kind": "work"})
    for c in account.running_costs:
        per = {"monthly": "month", "quarterly": "3 months", "yearly": "year"}.get(c.interval)
        for d in c.charge_dates(today + dt.timedelta(days=UPCOMING_DAYS)):
            g = group(d)
            g["lines"].append({"title": c.title, "amount": float(c.value_gbp or 0), "kind": "renewal" if per else "one-off",
                               "period": per})
            if c.covered:
                g["deductions"].append({"title": f"{deduction}: {c.title}", "amount": float(c.value_gbp or 0)})
    for p in account.payments:
        group(p.paid_at)["payments"].append({"title": "Payment received" + (f" ({p.method})" if p.method else ""),
                                             "amount": float(p.amount_gbp or 0)})
    out = []
    for d, g in sorted(groups.items(), key=lambda x: x[0], reverse=True):
        charges = round(sum(l["amount"] for l in g["lines"]), 2)
        covered = round(sum(x["amount"] for x in g["deductions"]), 2)
        paid = round(sum(x["amount"] for x in g["payments"]), 2)
        due = round(charges - covered - paid, 2)
        if d > today:
            status = "Upcoming"
        elif charges and covered >= charges:
            status = "Covered"
        elif due <= 0 and paid:
            status = "Paid"
        elif due > 0:
            status = "Due"
        else:
            status = "Payment"
        work = [l["title"] for l in g["lines"] if l["kind"] == "work"]
        titles = (["Website build & launch"] if len(work) > 1 else work) + [l["title"] for l in g["lines"] if l["kind"] != "work"]
        g.update(charges=charges, covered=covered, paid=paid, due=max(due, 0), status=status, upcoming=d > today,
                 summary=_summary(titles) or ("Payment" if paid else ""))
        out.append(g)
    return out


def _summary(titles):
    if not titles:
        return ""
    if len(titles) <= 2:
        return " & ".join(titles)
    return f"{titles[0]} + {len(titles) - 1} more"


def summary(account, today=None):
    today = today or dt.date.today()
    tx = transactions(account, today)
    past = [t for t in tx if not t["upcoming"]]
    costs = list(account.running_costs)
    starts = [t["date"] for t in past]
    since = min(starts) if starts else None
    work = [j for j in account.jobs if j.status == "done" and float(j.price_gbp or 0) > 0]
    covered_so_far = round(sum(t["covered"] for t in past), 2)
    periods = {}                                   # {2026: [("2026-11", "November 2026"), ...]} newest first
    for t in tx:
        key = t["date"].strftime("%Y-%m")
        months = periods.setdefault(t["date"].year, [])
        if key not in [k for k, _ in months]:
            months.append((key, t["date"].strftime("%B %Y")))
    return {
        "transactions": tx, "since": since, "periods": periods,
        "total_price": round(sum(t["charges"] for t in past), 2),
        "saved": covered_so_far, "covered_so_far": covered_so_far,
        "paid": round(sum(t["paid"] for t in past), 2),
        "covered_monthly": round(sum(c.monthly for c in costs if c.covered), 2),
        "value_total": round(sum(t["charges"] for t in past), 2),
        "work_total": round(sum(float(j.price_gbp or 0) for j in work), 2),
        "months": round((today - since).days / (365.25 / 12), 1) if since else 0,
        "all_costs": costs, "covered": [c for c in costs if c.covered],
        "my_monthly": round(sum(c.my_monthly or 0 for c in costs), 2),
    }


def find(account, ref):
    return next((t for t in transactions(account) if t["ref"] == ref), None)


def _setting(key):
    from models import db
    from models.core import SystemState
    row = db.session.get(SystemState, key)
    return (row.value or "").strip() if row else ""


def support_options():
    """Ways to support HapiTech, from Admin → Settings. PayPal: an email address (or a PayPal.me / PayPal link);
    Revolut: a checkout link. Returns [] when none are set."""
    from urllib.parse import quote
    out = []
    pp = _setting("support_paypal")
    if pp:
        if "@" in pp and not pp.startswith("http"):
            base = ("https://www.paypal.com/donate/?business=" + quote(pp) +
                    "&no_recurring=1&currency_code=GBP&item_name=" + quote("Support HapiTech"))
            out.append({"key": "paypal", "label": "PayPal", "sub": "Card or PayPal", "url": base, "amount_param": "&amount={n}"})
        elif pp.startswith("https://"):
            me = "paypal.me/" in pp.lower()
            out.append({"key": "paypal", "label": "PayPal", "sub": "Card or PayPal", "url": pp.rstrip("/"),
                        "amount_param": "/{n}GBP" if me else ""})
    rv = _setting("support_revolut")
    if rv.startswith("https://"):
        out.append({"key": "revolut", "label": "Revolut", "sub": "Card, Apple Pay or Google Pay", "url": rv, "amount_param": ""})
    return out


def donate_url():
    """Kept for older callers: the first support link, or None."""
    opts = support_options()
    return opts[0]["url"] if opts else None
