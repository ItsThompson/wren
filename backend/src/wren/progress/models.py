"""Progress ORM: one ``progress`` row per ``(user_id, roadmap_id)`` (spec §04, 11).

Progress is the second top-level entity, stored separately from the roadmap
definition (one roadmap : many progress records). The composite primary key
``(user_id, roadmap_id)`` enforces the "one record per (user, roadmap)" rule at
the database, so ``follow`` and every ``progress_update`` upsert into the same
row. ``checked`` holds the explicit-set map as JSONB (only checked items are
retained); ``deadline`` is the optional per-user date (its write lands in Ticket
17). ``user_id`` is a ``users.id`` and ``roadmap_id`` a ``roadmaps.id`` (no hard
FK, keeping the domains independently migratable, as accounts/roadmaps do).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wren.core.orm import Base
from wren.roadmaps.models import ROADMAP_ID_MAX_LENGTH


class ProgressRecord(Base):
    """A user's progress against one roadmap. ``checked`` is the explicit-set map."""

    __tablename__ = "progress"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    roadmap_id: Mapped[str] = mapped_column(String(ROADMAP_ID_MAX_LENGTH), primary_key=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    checked: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
