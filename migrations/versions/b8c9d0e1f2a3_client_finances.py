"""client finances: amount owed + message

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-23 20:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts') as b:
        b.add_column(sa.Column('balance_gbp', sa.Numeric(10, 2), nullable=True))
        b.add_column(sa.Column('billing_note', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('accounts') as b:
        b.drop_column('billing_note')
        b.drop_column('balance_gbp')
