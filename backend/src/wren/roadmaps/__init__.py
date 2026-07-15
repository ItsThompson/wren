"""The roadmaps domain: authoring spine for learning roadmaps (spec sections 04-06).

Mirrors the accounts domain layout (config / models / schemas / repository /
service / api / wiring) plus the pure deep modules the service composes
(``slugs`` for ID minting, ``assembly`` for turning ordered authoring input into
the persisted ID-keyed structure). Later slices extend this domain with patch,
validate, publish, fork, and the read projections.
"""
