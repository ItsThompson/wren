"""onboarding: per-account onboarding-completion flag on ``users``

Adds the ``users.has_completed_onboarding`` boolean. The column is added with a
non-null ``server_default false`` so the DDL is safe on the already-populated
table; the backfill then flips every pre-existing row to ``true`` (existing
accounts are treated as already onboarded, US-GUARD-04). New rows inserted after
this migration default to ``false`` at the ORM level (``register`` sets it
explicitly), so the server default is a safety net, not the new-user path.
Chained after the progress migration to keep a single linear head.

Revision ID: 0006_onboarding
Revises: 0005_progress
Create Date: 2026-07-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_onboarding"
down_revision: str | None = "0005_progress"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "has_completed_onboarding",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Backfill: every account that existed before this feature is already onboarded.
    op.execute("UPDATE users SET has_completed_onboarding = true")


def downgrade() -> None:
    op.drop_column("users", "has_completed_onboarding")
