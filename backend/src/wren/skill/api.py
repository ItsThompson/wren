"""External REST adapter serving the shipped ``SKILL.md`` at ``GET /skill``.

The authoring guidance is public: it is
generic agent guidance, not user data, and an agent must be able to fetch it
without a session or bearer (its access level is declared ``PUBLIC`` in
``wren.core.route_registry``). The MCP tool descriptions point agents here.

The router is a thin transport adapter: it loads the bundled markdown once at
construction (fail-fast if missing) and serves that cached content as
``text/markdown``. Content loading lives in the dependency-free
:mod:`wren.skill.content` module.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from wren.skill.content import SKILL_MEDIA_TYPE, read_skill_markdown

SKILL_ENDPOINT = "/skill"


def create_skill_router() -> APIRouter:
    """Build the ``GET /skill`` router, loading the guidance once at startup."""
    router = APIRouter(tags=["skill"])
    # Loaded eagerly (immutable at runtime): a missing file fails app startup
    # rather than surfacing a broken endpoint on the first request.
    skill_markdown = read_skill_markdown()

    @router.get(
        SKILL_ENDPOINT,
        response_class=Response,
        responses={
            200: {
                "description": "The shipped SKILL.md authoring guidance (Markdown).",
                "content": {"text/markdown": {"schema": {"type": "string"}}},
            }
        },
    )
    async def get_skill() -> Response:
        # Served for download/copy; the SKILL is versioned in the repo at
        # skill/SKILL.md and bundled with the backend image.
        return Response(content=skill_markdown, media_type=SKILL_MEDIA_TYPE)

    return router
