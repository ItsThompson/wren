"""Backend test suite package.

Packaged (``__init__.py`` present + ``pythonpath = ["src", "."]``) so tests use
absolute imports rooted at ``tests`` (e.g. ``from tests.support.fakes.roadmaps_fakes
import ...``). This gives every test module a unique dotted name, resolving the
duplicate-basename collisions the old flat layout tolerated by accident.

``conftest.py`` stays at this package root: pytest resolves conftest fixtures
upward only, so moving it would break ``postgres_url`` / ``make_settings``
discovery suite-wide.
"""
