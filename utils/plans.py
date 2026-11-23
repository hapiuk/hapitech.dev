# utils/plans.py — what each client is on. The "Friends plan" is for our first clients: everything included,
# free until a set date, then the normal monthly price.
import datetime as dt

MONTHLY_PRICE = 25                                   # £ a month after the Friends plan
FRIENDS_DEFAULT_END = dt.date(2027, 2, 28)           # "until February": free to the end of Feb 2027


def friends_end_default():
    return max(FRIENDS_DEFAULT_END, dt.date.today())


def describe(addon):
    """Plain-English summary for screens and emails, or None if no plan."""
    if not addon:
        return None
    ends = addon.trial_ends_at
    if addon.status == "friends":
        after = ends + dt.timedelta(days=1) if ends else None
        return {"name": "Friends plan", "free_until": ends, "charge_from": after, "price": MONTHLY_PRICE,
                "line": (f"Everything included, free until {ends:%-d %B %Y}. "
                         f"From {after:%-d %B %Y} it's £{MONTHLY_PRICE} a month.") if ends else "Everything included."}
    if addon.status == "trial":
        return {"name": "Free trial", "free_until": ends, "price": MONTHLY_PRICE,
                "line": f"Free trial until {ends:%-d %B %Y}." if ends else "Free trial."}
    if addon.status == "active":
        return {"name": "Monthly plan", "price": MONTHLY_PRICE, "line": f"£{MONTHLY_PRICE} a month. Everything included."}
    return {"name": "Paused", "line": "Paused. Ask Aaron to switch it back on."}
