"""tasks + task_notes: Aaron's own to-do tickets in the admin dashboard (client or HapiTech infra),
optional link to a change request, remind-on date, and a notes thread (Aaron / Claude / Client).

Revision ID: d2e3f4a5b6c7
Revises: b0c1d2e3f4a5
"""
from alembic import op
import sqlalchemy as sa

revision = 'd2e3f4a5b6c7'
down_revision = 'b0c1d2e3f4a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), index=True),
        sa.Column("change_request_id", sa.Integer, sa.ForeignKey("change_requests.id"), index=True),
        sa.Column("remind_on", sa.Date),
        sa.Column("reminded_at", sa.DateTime),
        sa.Column("done_at", sa.DateTime),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "task_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id"), nullable=False, index=True),
        sa.Column("author_kind", sa.String(20), nullable=False, server_default="aaron"),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("task_notes")
    op.drop_table("tasks")
