"""PRM tests: the Protected Resource Metadata document + 401 challenge (RFC 9728)."""

from __future__ import annotations

from wren_mcp.config import PRM_PATH
from wren_mcp.prm import (
    build_prm_document,
    prm_resource_metadata_url,
    www_authenticate_challenge,
)

_RESOURCE = "https://mcp.usewren.com"
_ISSUER = "https://api.usewren.com"


def test_prm_document_shape() -> None:
    document = build_prm_document(resource=_RESOURCE, issuer=_ISSUER)

    assert document["resource"] == _RESOURCE
    # The PRM advertises the backend AS as the authorization server for this RS.
    assert document["authorization_servers"] == [_ISSUER]
    assert "roadmaps:read" in document["scopes_supported"]
    assert "roadmaps:write" in document["scopes_supported"]
    assert "progress:write" in document["scopes_supported"]
    assert document["bearer_methods_supported"] == ["header"]


def test_prm_urls_are_built_from_pinned_config() -> None:
    # The RS sits behind the same tunnel as the AS, so URLs come from pinned
    # config, never a request host (the Site-URL gotcha).
    assert prm_resource_metadata_url(_RESOURCE) == f"{_RESOURCE}{PRM_PATH}"
    assert prm_resource_metadata_url("https://mcp.usewren.com/") == f"{_RESOURCE}{PRM_PATH}"


def test_www_authenticate_challenge_points_at_the_prm_document() -> None:
    challenge = www_authenticate_challenge(_RESOURCE)

    assert challenge == f'Bearer resource_metadata="{_RESOURCE}{PRM_PATH}"'
