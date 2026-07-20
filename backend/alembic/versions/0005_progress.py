"""progress: per-user roadmap-progress table

Adds the ``progress`` table: one row per
``(user_id, roadmap_id)`` holding the explicit-set ``checked`` map as JSONB plus
an optional per-user ``deadline``. The composite primary key enforces the
one-record-per-(user, roadmap) rule, so follow and every update upsert the same
row. An index on ``roadmap_id`` backs the follower-count query behind the
delete-only-if-zero-followers guard. Chained after the OAuth
migration to keep a single linear head.

Revision ID: 0005_progress
Revises: 0004_oauth
Create Date: 2026-07-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_progress"
down_revision: str | None = "0004_oauth"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "progress",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("roadmap_id", sa.String(length=120), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("checked", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "roadmap_id", name="pk_progress"),
    )
    op.create_index("ix_progress_roadmap_id", "progress", ["roadmap_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_progress_roadmap_id", table_name="progress")
    op.drop_table("progress")
