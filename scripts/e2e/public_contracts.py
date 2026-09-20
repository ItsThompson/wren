#!/usr/bin/env python3
"""Validate public OAuth discovery documents at the E2E boundary."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence


def is_authorization_server_metadata(document: object, expected_issuer: str) -> bool:
    if not isinstance(document, Mapping):
        return False
    return document.get("issuer") == expected_issuer and document.get("jwks_uri") == (
        f"{expected_issuer}/jwks"
    )


def is_protected_resource_metadata(
    document: object,
    expected_resource: str,
    expected_authorization_server: str,
) -> bool:
    if not isinstance(document, Mapping):
        return False
    authorization_servers = document.get("authorization_servers")
    return (
        document.get("resource") == expected_resource
        and isinstance(authorization_servers, Sequence)
        and not isinstance(authorization_servers, (str, bytes))
        and list(authorization_servers) == [expected_authorization_server]
    )


def main(arguments: list[str]) -> int:
    if not arguments:
        return 2
    try:
        document = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 1

    if arguments[0] == "authorization" and len(arguments) == 2:
        return int(not is_authorization_server_metadata(document, arguments[1]))
    if arguments[0] == "protected-resource" and len(arguments) == 3:
        return int(
            not is_protected_resource_metadata(document, arguments[1], arguments[2])
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
