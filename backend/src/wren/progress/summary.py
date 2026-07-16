"""``summary``: the pure progress-snapshot computation.

Derives the ``ProgressSnapshot`` (roadmap-wide + per-section completion) from a
roadmap definition and a progress record. This is a **derived read**: nothing here
is stored, it is recomputed on each read, so
the counts can never drift from the authoritative ``checked`` map. Pure and
framework-free, sharing the traversal helpers with ``next``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wren.core.section_counts import count_section, percent
from wren.progress.schemas import Progress, ProgressSnapshot, SectionProgress
from wren.progress.traversal import checked_item_ids

if TYPE_CHECKING:
    from wren.roadmaps import Roadmap


def summarize(roadmap: Roadmap, progress: Progress, *, detailed: bool) -> ProgressSnapshot:
    """Compute the completion snapshot for ``progress`` against ``roadmap``.

    Counts checked items per section (in ``section_order``) and overall.
    ``checked_ids`` is included only in ``detailed`` mode so the default read
    stays concise."""
    checked = checked_item_ids(roadmap, progress)
    sections: list[SectionProgress] = []
    total_all = 0
    checked_all = 0

    for section_id in roadmap.section_order:
        section = roadmap.sections.get(section_id)
        if section is None:
            continue
        total, done = count_section(section, checked)
        sections.append(
            SectionProgress(
                section_id=section_id,
                total_items=total,
                checked_items=done,
                percent=percent(done, total),
            )
        )
        total_all += total
        checked_all += done

    return ProgressSnapshot(
        roadmap_id=roadmap.id,
        total_items=total_all,
        checked_items=checked_all,
        percent=percent(checked_all, total_all),
        deadline=progress.deadline,
        sections=sections,
        checked_ids=sorted(checked) if detailed else None,
    )
