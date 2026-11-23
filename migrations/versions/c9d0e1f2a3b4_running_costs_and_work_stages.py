"""running costs per client + split the first website payment into its stages

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-24 10:00:00

"""
import datetime as dt

from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None

# Roland's domain was registered about 12 Dec 2025; Ray's site was started in Aug 2026.
STARTS = {"rolands-handyman": dt.date(2025, 12, 12), "ray-g-handyman": dt.date(2026, 8, 1)}
# The £500 "Website Build & Launch", split into what was actually done (adds up to £500).
STAGES = [("Website creation", "build", 300), ("Server setup", "hosting", 75), ("Deployment", "build", 50),
          ("Email setup", "other", 50), ("Domain registration", "other", 25)]
# value = what they'd pay to buy it themselves; my_cost = what it costs HapiTech (admin only)
COSTS = [("Server hosting", "hosting", 29.99, 40.00, "monthly", "Your cost is for the whole server (shared by every site on it)."),
         ("Email", "email", 25.00, 25.00, "yearly", None),
         ("Domain renewal", "domain", 12.00, 12.00, "yearly", "Placeholder price: check the registrar. Not charged yet; talk it through first.")]


def upgrade():
    op.create_table('running_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('value_gbp', sa.Numeric(10, 2), nullable=False),
        sa.Column('my_cost_gbp', sa.Numeric(10, 2), nullable=True),
        sa.Column('interval', sa.String(length=10), nullable=False),
        sa.Column('started_on', sa.Date(), nullable=True),
        sa.Column('ended_on', sa.Date(), nullable=True),
        sa.Column('covered', sa.Boolean(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'))
    with op.batch_alter_table('running_costs') as b:
        b.create_index('ix_running_costs_account_id', ['account_id'])

    conn = op.get_bind()
    now = dt.datetime.utcnow()
    accounts = sa.table('accounts', sa.column('id', sa.Integer), sa.column('slug', sa.String))
    jobs = sa.table('jobs', sa.column('id', sa.Integer), sa.column('account_id', sa.Integer), sa.column('title', sa.String),
                    sa.column('type', sa.String), sa.column('status', sa.String), sa.column('price_gbp', sa.Numeric),
                    sa.column('due_date', sa.Date), sa.column('notes', sa.Text),
                    sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime))
    costs = sa.table('running_costs', sa.column('account_id', sa.Integer), sa.column('title', sa.String),
                     sa.column('kind', sa.String), sa.column('value_gbp', sa.Numeric), sa.column('my_cost_gbp', sa.Numeric),
                     sa.column('interval', sa.String), sa.column('started_on', sa.Date), sa.column('covered', sa.Boolean),
                     sa.column('note', sa.String))
    for slug, start in STARTS.items():
        acc = conn.execute(sa.select(accounts.c.id).where(accounts.c.slug == slug)).scalar()
        if not acc:
            continue
        build = conn.execute(sa.select(jobs.c.id).where(jobs.c.account_id == acc, jobs.c.title == "Website Build & Launch",
                                                        jobs.c.price_gbp == 500)).scalar()
        if build:   # only if it's still the original single £500 job
            first, *rest = STAGES
            conn.execute(jobs.update().where(jobs.c.id == build).values(
                title=first[0], type=first[1], price_gbp=first[2], due_date=start, status="done",
                notes="Part of the original £500 website build and launch.", updated_at=now))
            for title, kind, price in rest:
                conn.execute(jobs.insert().values(account_id=acc, title=title, type=kind, status="done", price_gbp=price,
                                                  due_date=start, notes="Part of the original £500 website build and launch.",
                                                  created_at=now, updated_at=now))
        for title, kind, value, mine, interval, note in COSTS:
            conn.execute(costs.insert().values(account_id=acc, title=title, kind=kind, value_gbp=value, my_cost_gbp=mine,
                                               interval=interval, started_on=start, covered=True, note=note))


def downgrade():
    op.drop_table('running_costs')
