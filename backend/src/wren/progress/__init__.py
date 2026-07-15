"""The progress domain: following, explicit-set progress, and server-computed next.

Mirrors the accounts/roadmaps per-domain layout (models / schemas / repository /
service / api / api_internal / wiring) plus the pure deep modules the service
composes (``traversal`` shared helpers, ``summary`` for the derived snapshot,
``next`` for the server-side "what's next"). Progress is the second top-level
entity: one private record per ``(user, roadmap)``, stored
separately from the roadmap definition. Ticket 17 extends this with the deadline
write and the richer ``NextResult`` fields.
"""
