"""accounts: users table + refresh-jti blacklist

Adds the first domain tables on top of the empty baseline:
``users`` (public handle + email + bcrypt hash) and ``revoked_sessions`` (the
refresh-``jti`` blacklist for session revocation).

Revision ID: 0002_accounts
Revises: 0001_baseline
Create Date: 2026-07-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_accounts"
down_revision: str | None = "0001_baseline"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "revoked_sessions",
        sa.Column("jti", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("jti", name="pk_revoked_sessions"),
    )
    op.create_index("ix_revoked_sessions_user_id", "revoked_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_user_id", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
    op.drop_table("users")
