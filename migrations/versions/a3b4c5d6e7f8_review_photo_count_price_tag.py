"""reviews: photo count and Google's price tag (for reviews copied from Google)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-24 21:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'a3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reviews') as b:
        b.add_column(sa.Column('photo_count', sa.Integer(), nullable=False, server_default='0'))
        b.add_column(sa.Column('price_tag', sa.String(length=30), nullable=True))


def downgrade():
    with op.batch_alter_table('reviews') as b:
        b.drop_column('price_tag')
        b.drop_column('photo_count')
