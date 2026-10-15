"""create mttr metrics table and rollups

Revision ID: 0001
Revises: 
Create Date: 2026-10-08 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure timescaledb is available
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    # 1. Create the persistent incident_metrics table
    op.create_table(
        'incident_metrics',
        sa.Column('incident_id', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('outcome', sa.String(), nullable=True),
        sa.Column('fault_class', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('incident_id', 'started_at')
    )

    # 2. Convert to TimescaleDB hypertable chunked by started_at
    op.execute("SELECT create_hypertable('incident_metrics', 'started_at', if_not_exists => TRUE);")

    # 3. Create Continuous Aggregate for MTTR
    # Calculate avg duration for resolved incidents per hour, split by outcome
    #
    # WITH NO DATA is required, not an optimisation: a continuous aggregate
    # created WITH DATA runs a refresh, and TimescaleDB refuses that inside a
    # transaction block ("cannot run inside a transaction block"), which alembic
    # always provides. Without it this migration fails on a clean database and
    # nothing after it -- remediation_debt included -- ever gets created.
    # The view backfills on its refresh policy, or on demand via
    # CALL refresh_continuous_aggregate('mttr_hourly_rollup', NULL, NULL).
    op.execute("""
    CREATE MATERIALIZED VIEW mttr_hourly_rollup
    WITH (timescaledb.continuous) AS
    SELECT time_bucket('1 hour', started_at) AS bucket,
           outcome,
           AVG(duration_ms) AS mttr_avg_ms,
           COUNT(incident_id) AS incident_count
    FROM incident_metrics
    WHERE duration_ms IS NOT NULL
    GROUP BY bucket, outcome
    WITH NO DATA;
    """)

def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mttr_hourly_rollup;")
    op.drop_table('incident_metrics')
