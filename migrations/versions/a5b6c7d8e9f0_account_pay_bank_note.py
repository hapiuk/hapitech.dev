"""accounts.pay_bank (show bank transfer details on invoices) + pay_note (the payment message; blank =
default). Businesses that already filled in their bank details keep showing them.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
"""
from alembic import op
import sqlalchemy as sa

revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as b:
        b.add_column(sa.Column("pay_bank", sa.Boolean, nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("pay_note", sa.Text))
    op.execute("UPDATE accounts SET pay_bank = TRUE WHERE payment_details IS NOT NULL AND payment_details <> ''")


def downgrade():
    with op.batch_alter_table("accounts") as b:
        b.drop_column("pay_note")
        b.drop_column("pay_bank")
