"""Roadmaps ORM: one ``roadmaps`` row per roadmap (spec sections 04, 11).

The authoritative roadmap is the section-04 nested document, stored whole in the
``document`` JSONB column; the scalar columns (``owner``, ``status``,
``visibility``, ``revision``, ``title``) are a write-derived denormalized index
for the owner-scoping and listing queries later slices need, never a second
source of truth. The repository is the only writer, so it derives every column
from the domain :class:`~wren.roadmaps.schemas.Roadmap` and they cannot drift.

The roadmap ``id`` is the globally-unique ``{title-slug}-{short-random}`` slug;
``owner`` is a ``users.id`` (no hard FK, keeping the domains independently
migratable as the accounts domain does).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wren.core.orm import Base

# A roadmap ID is `{title-slug}-{token}`; the slug body is bounded generously so
# a long title still fits alongside the short random token.
ROADMAP_ID_MAX_LENGTH = 120


class RoadmapRecord(Base):
    """A roadmap definition. ``document`` holds the full section-04 roadmap."""

    __tablename__ = "roadmaps"

    id: Mapped[str] = mapped_column(String(ROADMAP_ID_MAX_LENGTH), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
