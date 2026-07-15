"""Tests for the bundled SKILL.md content and the canonical-copy drift guard (#27).

The human-edited canonical guidance lives at the repo root (``skill/SKILL.md``);
``wren.skill.content`` bundles a byte-identical copy beside the backend source so
it ships in the backend image. The drift test keeps the two in lockstep, mirroring
the committed ``frontend/openapi.json`` drift-check convention.
"""

from __future__ import annotations

from pathlib import Path

from wren.skill.content import (
    SKILL_MARKDOWN_PATH,
    SKILL_MEDIA_TYPE,
    read_skill_markdown,
)

# Repo root is three parents up from this test file (backend/tests -> backend -> repo).
_CANONICAL_SKILL_PATH = Path(__file__).resolve().parents[2] / "skill" / "SKILL.md"


def test_bundled_skill_matches_the_canonical_repo_root_copy() -> None:
    # If this fails after editing the canonical guidance, re-sync the bundled copy:
    #   cp skill/SKILL.md backend/src/wren/skill/SKILL.md
    assert _CANONICAL_SKILL_PATH.exists(), f"canonical SKILL missing at {_CANONICAL_SKILL_PATH}"
    assert SKILL_MARKDOWN_PATH.read_text(encoding="utf-8") == _CANONICAL_SKILL_PATH.read_text(
        encoding="utf-8"
    )


def test_media_type_is_utf8_markdown() -> None:
    # The guidance carries non-ASCII (the >= glyph in the validation contract), so
    # the charset is load-bearing, not decorative.
    assert SKILL_MEDIA_TYPE == "text/markdown; charset=utf-8"


def test_read_skill_markdown_returns_the_guidance_content() -> None:
    content = read_skill_markdown()
    # Load-bearing thesis + the concepts every roadmap author must honor.
    assert "Zone of Proximal Development" in content
    assert "you are the brain, not the app" in content
    # The three write paths are named and their roles distinguished.
    assert "create_roadmap_draft" in content
    assert "patch_roadmap_draft" in content
    assert "replace_roadmap_draft" in content
    assert "Import escape hatch only" in content
    # ID-addressing, the full validation contract, and the patch cycle rule.
    assert "never by array index" in content.lower() or "never by array index" in content
    assert "V1" in content and "V8" in content
    assert "transient-cycle rule" in content
    # Confirm-before-publish, since publish is one-way.
    assert "one-way" in content
    assert "explicit confirmation" in content.lower()
