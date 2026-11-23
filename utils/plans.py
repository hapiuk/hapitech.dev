# utils/plans.py — what each client is on. The "Friends plan" gives everything in the dashboard, on top of us
# looking after their website. It runs to a date and, by default, renews itself every 3 months.
# Clients never see prices here: just a friendly note that they're on the Friends plan.
import calendar
import datetime as dt

RENEW_MONTHS = 3


def add_months(d, months):
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def friends_end_default(months=RENEW_MONTHS):
    return add_months(dt.date.today(), months)


def start_friends(addon, until=None, renew_months=RENEW_MONTHS):
    addon.status = "friends"
    addon.trial_ends_at = until or friends_end_default(renew_months or RENEW_MONTHS)
    addon.renew_months = renew_months


def roll_forward(addon, today=None):
    """Auto-renew: push the end date on by renew_months until it's in the future. Returns True if changed."""
    today = today or dt.date.today()
    if addon.status != "friends" or not addon.renew_months or not addon.trial_ends_at:
        return False
    changed = False
    while addon.trial_ends_at < today:
        addon.trial_ends_at = add_months(addon.trial_ends_at, addon.renew_months)
        changed = True
    return changed


def describe(addon):
    """For screens. 'line' is what the CLIENT sees (never a price); 'admin' is the detail for Aaron."""
    if not addon:
        return None
    ends = addon.trial_ends_at
    if addon.status == "friends":
        renew = f"renews every {addon.renew_months} months" if addon.renew_months else "doesn't renew"
        return {"name": "Friends plan",
                "line": "Everything in your dashboard is included, on top of us looking after your website.",
                "admin": f"Runs to {ends:%-d %b %Y}, {renew}." if ends else f"No end date, {renew}."}
    if addon.status == "trial":
        return {"name": "Free trial", "line": "Everything in your dashboard is included while you try it out.",
                "admin": f"Trial to {ends:%-d %b %Y}." if ends else "Trial."}
    if addon.status == "active":
        return {"name": "Full plan", "line": "Everything in your dashboard is included.", "admin": "Paid plan."}
    return {"name": "Paused", "line": "Your dashboard is paused. Your website carries on as normal.", "admin": "Paused."}
