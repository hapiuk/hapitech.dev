"""accounts.languages: extra dashboard languages offered to this client (e.g. "lv"); blank = English only.
Roland and Ray get Latvian.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
"""
from alembic import op
import sqlalchemy as sa

revision = 'b0c1d2e3f4a5'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("accounts") as b:
        b.add_column(sa.Column("languages", sa.String(40)))
    op.execute("UPDATE accounts SET languages = 'lv' WHERE slug IN ('rolands-handyman', 'ray-g-handyman')")


def downgrade():
    with op.batch_alter_table("accounts") as b:
        b.drop_column("languages")
