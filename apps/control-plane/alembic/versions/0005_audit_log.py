"""append-only audit log with a hash chain

ARCHITECTURE.md specifies audit_log(id, incident_id, ts, actor, event, payload
JSONB, prev_hash, hash) and says append-only is "enforced by trigger, not
convention". AGENTS.md rule 8 names it a core guarantee and forbids an update or
delete route; a rule nothing enforces is a comment, so the enforcement is in the
database where no application bug can route around it.

Purely additive: a new table and a new trigger, nothing existing is touched.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("incident_id", sa.String(), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=False, unique=True),
    )
    op.create_index("ix_audit_log_incident_id", "audit_log", ["incident_id"])

    # Append-only, in the database. A revoked privilege would be cleaner but the
    # application and the migrations share one role here, and a role that cannot
    # UPDATE could not create the table either.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION kavach_audit_log_is_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_log is append-only (AGENTS.md rule 8); % refused', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION kavach_audit_log_is_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS kavach_audit_log_is_append_only()")
    op.drop_index("ix_audit_log_incident_id", table_name="audit_log")
    op.drop_table("audit_log")
