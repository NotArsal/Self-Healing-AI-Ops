"""create remediation_debt table

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'remediation_debt',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('incident_id', sa.String(), nullable=False),
        sa.Column('action_name', sa.String(), nullable=False),
        sa.Column('action_params', JSONB, nullable=False, server_default='{}'),
        sa.Column('trigger_type', sa.String(), nullable=False),
        sa.Column('trigger_condition', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('max_age_s', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add an index on status to speed up background polling
    op.create_index('ix_remediation_debt_status', 'remediation_debt', ['status'])

def downgrade() -> None:
    op.drop_index('ix_remediation_debt_status', table_name='remediation_debt')
    op.drop_table('remediation_debt')
