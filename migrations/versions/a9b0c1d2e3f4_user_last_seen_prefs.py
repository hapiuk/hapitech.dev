"""users.last_seen_at (last time they used the dashboard) and users.prefs (small personal settings)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
"""
from alembic import op
import sqlalchemy as sa

revision = 'a9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("last_seen_at", sa.DateTime()))
        b.add_column(sa.Column("prefs", sa.Text()))


def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("prefs")
        b.drop_column("last_seen_at")
