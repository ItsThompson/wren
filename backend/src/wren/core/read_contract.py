"""Cross-domain read-surface contract shared by roadmaps and progress.

``ResponseFormat`` is the ``concise | detailed`` switch on the study-time read
surface. It is a cross-domain truth: the roadmaps read endpoints/tools *and* the
progress ``get_next`` surface both accept it, so it lives here in ``core`` rather
than inside either domain's schema module. Domain read-projection modules keep
their own domain-local read types (e.g. ``SectionInclude``, ``SearchHit*`` in
``wren.roadmaps.read_schemas``); only the genuinely shared switch is hoisted.
"""

from __future__ import annotations

from enum import StrEnum


class ResponseFormat(StrEnum):
    """The ``concise | detailed`` switch on the read tools.

    Concise is roughly one-third the tokens and still carries the follow-up IDs;
    detailed adds the explanatory free-text (the node ``description``)."""

    CONCISE = "concise"
    DETAILED = "detailed"
