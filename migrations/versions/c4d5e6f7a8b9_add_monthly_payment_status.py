"""Add MonthlyPaymentStatus table for dot-calendar payment tracking

Revision ID: c4d5e6f7a8b9
Revises: ba2985044551
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'ba2985044551'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'monthly_payment_status',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(7), nullable=False),
        sa.Column('status', sa.String(10), nullable=False, server_default='DUE'),
        sa.Column('amount_gbp', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('marked_paid_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('entity_type', 'entity_id', 'month', name='uq_entity_month'),
    )
    op.create_index('ix_monthly_payment_status_entity', 'monthly_payment_status', ['entity_type', 'entity_id'])
    op.create_index('ix_monthly_payment_status_month', 'monthly_payment_status', ['month'])


def downgrade():
    op.drop_index('ix_monthly_payment_status_month')
    op.drop_index('ix_monthly_payment_status_entity')
    op.drop_table('monthly_payment_status')
