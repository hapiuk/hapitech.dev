"""reviews: Facebook recommends; accounts: Google / Facebook headline numbers

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-24 23:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'b4c5d6e7f8a9'
down_revision = 'a3b4c5d6e7f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reviews') as b:
        b.add_column(sa.Column('recommends', sa.Boolean(), nullable=True))
    with op.batch_alter_table('accounts') as b:
        b.add_column(sa.Column('google_rating', sa.Numeric(2, 1), nullable=True))
        b.add_column(sa.Column('google_count', sa.Integer(), nullable=True))
        b.add_column(sa.Column('facebook_url', sa.String(length=300), nullable=True))
        b.add_column(sa.Column('facebook_pct', sa.Integer(), nullable=True))
        b.add_column(sa.Column('facebook_count', sa.Integer(), nullable=True))
        b.add_column(sa.Column('reviews_synced_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('accounts') as b:
        for c in ('reviews_synced_at', 'facebook_count', 'facebook_pct', 'facebook_url', 'google_count', 'google_rating'):
            b.drop_column(c)
    with op.batch_alter_table('reviews') as b:
        b.drop_column('recommends')
