"""Shared in-memory test doubles used across domains.

Each fake substitutes the real Postgres boundary (the only true external
dependency) while the rest of the service layer runs for real, so the suite stays
sociable. Consumed cross-domain: ``accounts_fakes`` and ``roadmaps_fakes`` by
progress/roadmaps tests, ``progress_fakes`` / ``progress_builders`` by roadmaps
read tests. Domain-local doubles (``oauth_fakes``, ``roadmaps_read_builders``)
stay at the ``tests`` package root.
"""
