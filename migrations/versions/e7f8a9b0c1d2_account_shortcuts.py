"""accounts.shortcuts: quick links on the client's Jobs page (Bark, TaskRabbit, MyBuilder…)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-11-25 12:00:00

"""
import json

from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None

DEFAULT = [["Bark", "https://www.bark.com/en/gb/login/"], ["TaskRabbit", "https://www.taskrabbit.co.uk/login"],
           ["MyBuilder", "https://www.mybuilder.com/login"]]


def upgrade():
    with op.batch_alter_table('accounts') as b:
        b.add_column(sa.Column('shortcuts', sa.Text(), nullable=True))
    accounts = sa.table('accounts', sa.column('slug', sa.String), sa.column('shortcuts', sa.Text))
    for slug in ("rolands-handyman", "ray-g-handyman"):
        op.execute(accounts.update().where(accounts.c.slug == slug).values(shortcuts=json.dumps(DEFAULT)))


def downgrade():
    with op.batch_alter_table('accounts') as b:
        b.drop_column('shortcuts')
