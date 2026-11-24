"""accounts.pay_link_kind + pay_link: one online "Pay now" link per business (Revolut, PayPal, Monzo,
SumUp, Stripe or other), shown on unpaid invoices.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as b:
        b.add_column(sa.Column("pay_link_kind", sa.String(20)))
        b.add_column(sa.Column("pay_link", sa.String(300)))


def downgrade():
    with op.batch_alter_table("accounts") as b:
        b.drop_column("pay_link")
        b.drop_column("pay_link_kind")
