"""invoices.pay_clicked_at / pay_clicks: when the customer last opened the "Pay now" link (not proof of payment).

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7d8e9f0a1b2'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("invoices") as b:
        b.add_column(sa.Column("pay_clicked_at", sa.DateTime))
        b.add_column(sa.Column("pay_clicks", sa.Integer, nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("invoices") as b:
        b.drop_column("pay_clicks")
        b.drop_column("pay_clicked_at")
