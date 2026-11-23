"""reviews.reply_skipped_at: the business chose "no reply needed"

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-11-25 11:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reviews') as b:
        b.add_column(sa.Column('reply_skipped_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('reviews') as b:
        b.drop_column('reply_skipped_at')
