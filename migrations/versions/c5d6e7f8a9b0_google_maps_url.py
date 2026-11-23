"""accounts.google_maps_url: the client's Google Maps page (where the review export is run)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-25 09:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('accounts') as b:
        b.add_column(sa.Column('google_maps_url', sa.String(length=600), nullable=True))


def downgrade():
    with op.batch_alter_table('accounts') as b:
        b.drop_column('google_maps_url')
