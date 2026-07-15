"""The shipped ``SKILL.md`` authoring guidance served at ``GET /skill``.

The canonical, human-edited copy lives at the repository root (``skill/SKILL.md``).
This module bundles a byte-identical copy alongside the
backend source so it ships inside the backend image (whose build context is
``backend/`` and so cannot reach a repo-root file) and resolves the same way in
dev, tests, and the container. A drift test
(``tests/test_skill_content.py``) keeps the two copies in lockstep, mirroring the
committed ``frontend/openapi.json`` + drift-check convention: edit the repo-root
canonical copy, then re-sync this one (``cp skill/SKILL.md
backend/src/wren/skill/SKILL.md``).

Loaded once from disk at import time (the content is immutable at runtime); the
router closes over it. Reading is a pure, dependency-free concern kept out of the
transport adapter (``api.py``).
"""

from __future__ import annotations

from pathlib import Path

# ``text/markdown`` with a UTF-8 charset: the file is CommonMark and carries
# non-ASCII (e.g. the ``≥`` in the validation contract), so the charset is not
# optional. RFC 7763 registers ``text/markdown``.
SKILL_MEDIA_TYPE = "text/markdown; charset=utf-8"

# Bundled beside this module so it travels with the backend image.
SKILL_MARKDOWN_PATH = Path(__file__).parent / "SKILL.md"


def read_skill_markdown() -> str:
    """Return the shipped ``SKILL.md`` content as UTF-8 text.

    Raises ``FileNotFoundError`` if the bundled file is missing, which fails the
    app fast at startup (the router loads it eagerly) rather than serving a broken
    ``GET /skill`` at request time.
    """
    return SKILL_MARKDOWN_PATH.read_text(encoding="utf-8")
