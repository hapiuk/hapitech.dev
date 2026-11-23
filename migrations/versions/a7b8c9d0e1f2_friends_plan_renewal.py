"""friends plan auto-renewal

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-23 18:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('addons') as b:
        b.add_column(sa.Column('renew_months', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('addons') as b:
        b.drop_column('renew_months')
