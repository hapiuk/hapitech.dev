"""support HapiTech: PayPal + Revolut payment options (only set if not already set)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-24 16:00:00

"""
import datetime as dt

from alembic import op
import sqlalchemy as sa

revision = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None

DEFAULTS = {"support_paypal": "aaron@hapitech.dev",
            "support_revolut": "https://checkout.revolut.com/pay/6234d885-bfbc-48b6-88ba-bd3134ce4d52"}


def upgrade():
    conn = op.get_bind()
    state = sa.table('system_state', sa.column('key', sa.String), sa.column('value', sa.Text), sa.column('updated_at', sa.DateTime))
    for k, v in DEFAULTS.items():
        if conn.execute(sa.select(state.c.key).where(state.c.key == k)).scalar() is None:
            conn.execute(state.insert().values(key=k, value=v, updated_at=dt.datetime.utcnow()))


def downgrade():
    pass
