"""roadmaps: roadmap definitions table

Adds the ``roadmaps`` table: scalar index columns
(owner / status / visibility / revision / title) plus the authoritative
roadmap document as JSONB. Chained after the accounts migration to
keep a single linear head.

Revision ID: 0003_roadmaps
Revises: 0002_accounts
Create Date: 2026-07-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_roadmaps"
down_revision: str | None = "0002_accounts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "roadmaps",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("owner", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_roadmaps"),
    )
    op.create_index("ix_roadmaps_owner", "roadmaps", ["owner"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_roadmaps_owner", table_name="roadmaps")
    op.drop_table("roadmaps")
