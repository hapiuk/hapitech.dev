"""work requests: which client a HapiTech job is for, and what they offered

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-24 19:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('leads') as b:
        b.add_column(sa.Column('for_account_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('offer_gbp', sa.Numeric(10, 2), nullable=True))
        b.create_index('ix_leads_for_account_id', ['for_account_id'])
        b.create_foreign_key('fk_leads_for_account', 'accounts', ['for_account_id'], ['id'])


def downgrade():
    with op.batch_alter_table('leads') as b:
        b.drop_constraint('fk_leads_for_account', type_='foreignkey')
        b.drop_index('ix_leads_for_account_id')
        b.drop_column('offer_gbp')
        b.drop_column('for_account_id')
