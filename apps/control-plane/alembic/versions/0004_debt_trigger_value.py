"""add trigger_value to remediation_debt

The debt trigger carries a dwell time ("healthy for 600s") that was declared in
kavach.yaml but never persisted, so the checker evaluated the condition with
value=0 and repaid the instant the application first looked healthy.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'remediation_debt',
        sa.Column('trigger_value', sa.Float(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('remediation_debt', 'trigger_value')
