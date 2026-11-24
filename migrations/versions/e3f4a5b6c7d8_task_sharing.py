"""Tasks the client can see: tasks.shared + task_notes.shared (client comments / replies to them),
tasks.lead_id (an accepted HapiTech job becomes a task). Change requests already turned into tasks are shared.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as b:
        b.add_column(sa.Column("shared", sa.Boolean, nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id", name="fk_tasks_lead_id")))
        b.create_index("ix_tasks_lead_id", ["lead_id"])
    with op.batch_alter_table("task_notes") as b:
        b.add_column(sa.Column("shared", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute("UPDATE tasks SET shared = TRUE WHERE change_request_id IS NOT NULL")
    op.execute("UPDATE task_notes SET shared = TRUE WHERE author_kind = 'client' AND task_id IN "
               "(SELECT id FROM tasks WHERE change_request_id IS NOT NULL)")


def downgrade():
    with op.batch_alter_table("task_notes") as b:
        b.drop_column("shared")
    with op.batch_alter_table("tasks") as b:
        b.drop_index("ix_tasks_lead_id")
        b.drop_column("lead_id")
        b.drop_column("shared")
