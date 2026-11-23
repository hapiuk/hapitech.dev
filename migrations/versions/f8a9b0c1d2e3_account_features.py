"""accounts.features: which dashboard sections a client gets (blank = everything)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
from alembic import op
import sqlalchemy as sa

revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as b:
        b.add_column(sa.Column("features", sa.Text()))


def downgrade():
    with op.batch_alter_table("accounts") as b:
        b.drop_column("features")
