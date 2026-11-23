# utils/plan_value.py — what a client has had from HapiTech: the work done, plus the running costs HapiTech
# has covered for them so far (at what they'd pay to buy it themselves). Shown on their "My plan" page, and
# with HapiTech's own costs on the admin Money tab, as a pricing reference.
import datetime as dt

DONATE_KEY = "donate_url"


def summary(account, today=None):
    today = today or dt.date.today()
    work = sorted([j for j in account.jobs if j.status == "done" and float(j.price_gbp or 0) > 0],
                  key=lambda j: (j.due_date or dt.date.min, j.id))
    work_total = sum(float(j.price_gbp or 0) for j in work)
    costs = [c for c in account.running_costs if not c.ended_on or c.ended_on >= (c.started_on or today)]
    covered = [c for c in costs if c.covered]
    covered_so_far = round(sum(c.value_so_far(today) for c in covered), 2)
    paid = round(sum(float(p.amount_gbp or 0) for p in account.payments), 2)
    starts = [c.started_on for c in costs if c.started_on] + [j.due_date for j in work if j.due_date]
    since = min(starts) if starts else None
    mine_monthly = sum(c.my_monthly or 0 for c in costs)
    # a statement: each order (work done on the same date = one order), then each running cost priced
    # from when it started, minus what the plan covers. Saved = what the plan has covered.
    orders, by_date = [], {}
    for j in work:
        by_date.setdefault(j.due_date, []).append(j)
    for d, js in sorted(by_date.items(), key=lambda x: x[0] or dt.date.min):
        title = "Website build & launch" if len(js) > 1 and any(j.type == "build" for j in js) else js[0].title
        orders.append({"kind": "work", "date": d, "title": title, "parts": js,
                       "price": round(sum(float(j.price_gbp or 0) for j in js), 2)})
    for c in sorted(costs, key=lambda c: (c.started_on or today, c.id)):
        so_far = c.value_so_far(today)
        orders.append({"kind": "cost", "date": c.started_on, "title": c.title, "cost": c, "price": so_far,
                       "months": round(c.months_active(today), 1), "covered": so_far if c.covered else 0})
    total_price = round(sum(o["price"] for o in orders), 2)
    return {
        "orders": orders, "total_price": total_price, "saved": covered_so_far,
        "work": work, "work_total": round(work_total, 2),
        "covered": covered, "covered_monthly": round(sum(c.monthly for c in covered), 2),
        "covered_so_far": covered_so_far,
        "value_total": round(work_total + covered_so_far, 2),
        "paid": paid, "since": since,
        "months": round((today - since).days / (365.25 / 12), 1) if since else 0,
        "all_costs": costs, "my_monthly": round(mine_monthly, 2),
    }


def donate_url():
    from models import db
    from models.core import SystemState
    row = db.session.get(SystemState, DONATE_KEY)
    return (row.value or "").strip() if row and (row.value or "").strip().startswith("https://") else None
