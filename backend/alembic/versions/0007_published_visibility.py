"""Rename roadmap visibility to publication visibility.

The scalar index and JSON document are rewritten in one transaction. The
preflight rejects invalid or ambiguous legacy rows before any row changes.

Revision ID: 0007_published_visibility
Revises: 0006_onboarding
Create Date: 2026-07-19
"""

from __future__ import annotations

from alembic import op

revision: str = "0007_published_visibility"
down_revision: str | None = "0006_onboarding"
branch_labels: str | None = None
depends_on: str | None = None


_UPGRADE_PREFLIGHT = """
DO $published_visibility_upgrade$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM roadmaps
        WHERE jsonb_typeof(document) IS DISTINCT FROM 'object'
           OR visibility NOT IN ('public', 'private')
           OR document ? 'published_visibility'
           OR (
                document ? 'visibility'
                AND (
                    jsonb_typeof(document -> 'visibility') IS DISTINCT FROM 'string'
                    OR document ->> 'visibility' NOT IN ('public', 'private')
                    OR document ->> 'visibility' IS DISTINCT FROM visibility
                )
           )
    ) THEN
        RAISE EXCEPTION 'published visibility migration preflight failed';
    END IF;
END
$published_visibility_upgrade$
"""

_DOWNGRADE_PREFLIGHT = """
DO $published_visibility_downgrade$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM roadmaps
        WHERE jsonb_typeof(document) IS DISTINCT FROM 'object'
           OR published_visibility NOT IN ('public', 'private')
           OR document ? 'visibility'
           OR NOT (document ? 'published_visibility')
           OR jsonb_typeof(document -> 'published_visibility') IS DISTINCT FROM 'string'
           OR document ->> 'published_visibility' NOT IN ('public', 'private')
           OR document ->> 'published_visibility' IS DISTINCT FROM published_visibility
    ) THEN
        RAISE EXCEPTION 'published visibility downgrade preflight failed';
    END IF;
END
$published_visibility_downgrade$
"""

_UPGRADE_POSTFLIGHT = """
DO $published_visibility_upgrade_postflight$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM roadmaps
        WHERE published_visibility NOT IN ('public', 'private')
           OR jsonb_typeof(document) IS DISTINCT FROM 'object'
           OR NOT (document ? 'published_visibility')
           OR document ? 'visibility'
           OR jsonb_typeof(document -> 'published_visibility') IS DISTINCT FROM 'string'
           OR document ->> 'published_visibility' IS DISTINCT FROM published_visibility
    ) THEN
        RAISE EXCEPTION 'published visibility migration postflight failed';
    END IF;
END
$published_visibility_upgrade_postflight$
"""

_DOWNGRADE_POSTFLIGHT = """
DO $published_visibility_downgrade_postflight$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM roadmaps
        WHERE visibility NOT IN ('public', 'private')
           OR jsonb_typeof(document) IS DISTINCT FROM 'object'
           OR NOT (document ? 'visibility')
           OR document ? 'published_visibility'
           OR jsonb_typeof(document -> 'visibility') IS DISTINCT FROM 'string'
           OR document ->> 'visibility' IS DISTINCT FROM visibility
    ) THEN
        RAISE EXCEPTION 'published visibility downgrade postflight failed';
    END IF;
END
$published_visibility_downgrade_postflight$
"""


def upgrade() -> None:
    op.execute(_UPGRADE_PREFLIGHT)
    op.execute(
        """
        UPDATE roadmaps
        SET document = CASE
            WHEN document ? 'visibility'
                THEN (document - 'visibility') || jsonb_build_object(
                    'published_visibility', document -> 'visibility'
                )
            ELSE document || jsonb_build_object(
                'published_visibility', to_jsonb(visibility)
            )
        END
        """
    )
    op.alter_column("roadmaps", "visibility", new_column_name="published_visibility")
    op.execute(_UPGRADE_POSTFLIGHT)


def downgrade() -> None:
    op.execute(_DOWNGRADE_PREFLIGHT)
    op.execute(
        """
        UPDATE roadmaps
        SET document = (document - 'published_visibility') || jsonb_build_object(
            'visibility', document -> 'published_visibility'
        )
        """
    )
    op.alter_column("roadmaps", "published_visibility", new_column_name="visibility")
    op.execute(_DOWNGRADE_POSTFLIGHT)
