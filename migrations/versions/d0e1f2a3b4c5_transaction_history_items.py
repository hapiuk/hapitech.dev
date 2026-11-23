"""transaction history: more maintained items, email £50/yr, domain renews a year after registration,
first payments backdated to each site's start

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-24 14:00:00

"""
import datetime as dt

from alembic import op
import sqlalchemy as sa

revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None

STARTS = {"rolands-handyman": dt.date(2025, 12, 12), "ray-g-handyman": dt.date(2026, 8, 1)}
# (title, kind, value £, interval, HapiTech's own cost £ or None, note) — all covered by the Friends plan for now
NEW = [("Server maintenance", "hosting", 15.00, "monthly", None, "Keeping the server patched, monitored and backed up."),
       ("Security updates", "hosting", 10.00, "monthly", None, "Software and security updates for the website."),
       ("SSL certificate renewal", "hosting", 9.99, "quarterly", 0, "The padlock in the browser. Renewed every 3 months."),
       ("Terms & privacy pages", "other", 75.00, "once", None, "Written and added to the website.")]


def upgrade():
    conn = op.get_bind()
    accounts = sa.table('accounts', sa.column('id', sa.Integer), sa.column('slug', sa.String))
    costs = sa.table('running_costs', sa.column('id', sa.Integer), sa.column('account_id', sa.Integer),
                     sa.column('title', sa.String), sa.column('kind', sa.String), sa.column('value_gbp', sa.Numeric),
                     sa.column('my_cost_gbp', sa.Numeric), sa.column('interval', sa.String), sa.column('started_on', sa.Date),
                     sa.column('covered', sa.Boolean), sa.column('note', sa.String))
    payments = sa.table('payments', sa.column('id', sa.Integer), sa.column('account_id', sa.Integer),
                        sa.column('paid_at', sa.Date), sa.column('ref', sa.String))
    for slug, start in STARTS.items():
        acc = conn.execute(sa.select(accounts.c.id).where(accounts.c.slug == slug)).scalar()
        if not acc:
            continue
        conn.execute(costs.update().where(costs.c.account_id == acc, costs.c.kind == "email").values(value_gbp=50))
        conn.execute(costs.update().where(costs.c.account_id == acc, costs.c.kind == "domain", costs.c.started_on == start)
                     .values(started_on=dt.date(start.year + 1, start.month, start.day),
                             note="Registered with the website build; renews every year after that. Placeholder price."))
        have = {r[0] for r in conn.execute(sa.select(costs.c.title).where(costs.c.account_id == acc))}
        for title, kind, value, interval, mine, note in NEW:
            if title not in have:
                conn.execute(costs.insert().values(account_id=acc, title=title, kind=kind, value_gbp=value, my_cost_gbp=mine,
                                                   interval=interval, started_on=start, covered=True, note=note))
        conn.execute(payments.update().where(payments.c.account_id == acc, payments.c.ref == "migrated from webdev_jobs")
                     .values(paid_at=start))


def downgrade():
    pass
