"""passwordless login + data minimisation: wipe stored password hashes, customer contact
details on review requests, and raw IPs on login attempts.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET password_hash = ''"))
    conn.execute(sa.text("UPDATE review_requests SET contact = NULL"))
    conn.execute(sa.text("DELETE FROM login_attempts"))     # held raw IPs; now stored as keyed hashes


def downgrade():
    pass    # wiped data can't be restored (that's the point)
