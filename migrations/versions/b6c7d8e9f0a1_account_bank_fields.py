"""accounts bank transfer details as separate fields: bank_name, bank_account_name, bank_sort_code,
bank_account_number (the old free-text payment_details stays as a fallback).

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
"""
from alembic import op
import sqlalchemy as sa

revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as b:
        b.add_column(sa.Column("bank_name", sa.String(80)))
        b.add_column(sa.Column("bank_account_name", sa.String(120)))
        b.add_column(sa.Column("bank_sort_code", sa.String(8)))
        b.add_column(sa.Column("bank_account_number", sa.String(8)))


def downgrade():
    with op.batch_alter_table("accounts") as b:
        for c in ("bank_account_number", "bank_sort_code", "bank_account_name", "bank_name"):
            b.drop_column(c)
