"""baseline (empty)

Establishes the migration chain root and creates the ``alembic_version`` table on
``upgrade head``. No schema yet: this baseline is DB plumbing only. Later
revisions add the first domain tables on top of this baseline.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-14

"""

from __future__ import annotations

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
