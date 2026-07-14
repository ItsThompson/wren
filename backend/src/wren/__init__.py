"""Wren backend: modular-monolith learning-roadmap platform.

Two ASGI apps (external :8000, internal :8001) assembled from one factory over a
shared service layer. This package root stays import-light; see ``wren.core`` for
the shared kit and ``wren.api`` / ``wren.api_internal`` for the app entrypoints.
"""
