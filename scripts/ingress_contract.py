#!/usr/bin/env python3
"""Validate and render the Wren ingress contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    sys.path.insert(0, str(ROOT))

from scripts.ingress_models import (  # noqa: E402
    AllMatch,
    AllowlistMatch,
    IngressContract,
    PathsMatch,
    Route,
)

CONTRACT_PATH = ROOT / "deployments/ingress/contract.json"
CLOUDFLARE_PATH = ROOT / "deployments/cloudflare/config.yml"
NGINX_PATH = ROOT / "e2e/ingress/nginx.conf"


def load_contract(path: Path = CONTRACT_PATH) -> IngressContract:
    with path.open(encoding="utf-8") as contract_file:
        return IngressContract.model_validate(json.load(contract_file))


def validate_contract(contract: object) -> IngressContract:
    if isinstance(contract, IngressContract):
        return contract
    return IngressContract.model_validate(contract)


def _match_path(match: object, path: str) -> bool:
    if isinstance(match, AllMatch):
        return True
    expression = _path_regex(match)
    return expression is not None and re.fullmatch(expression, path) is not None


def resolve_route(contract: object, host_id: str, path: str) -> Route:
    """Return the first typed route selected for a host and path."""
    typed_contract = validate_contract(contract)
    for host in typed_contract.hosts:
        if host.id == host_id:
            for route in host.routes:
                if _match_path(route.match, path):
                    return route.model_copy(deep=True)
            break
    return Route(
        id="catch-all",
        match=AllMatch(kind="all"),
        action=typed_contract.catch_all.model_copy(deep=True),
    )


def _escaped_path(path: str) -> str:
    return re.escape(path.lstrip("/")).replace("\\-", "-")


def _path_regex(match: object) -> str | None:
    if isinstance(match, AllMatch):
        return None
    if isinstance(match, PathsMatch):
        if "/" in match.paths:
            alternatives = []
            for path in match.paths:
                canonical = path if path == "/" or not match.trailing_slash else path.rstrip("/")
                suffix = "" if canonical == "/" else "/?" if match.trailing_slash else ""
                alternatives.append(f"{_escaped_path(canonical)}{suffix}")
            if alternatives == [""]:
                return r"^/$"
            return rf"^/(?:{'|'.join(alternatives)})$"
        paths = [_escaped_path(path) for path in match.paths]
        path_expression = paths[0] if len(paths) == 1 else f"({'|'.join(paths)})"
        suffix = "/?" if match.trailing_slash else ""
        return rf"^/{path_expression}{suffix}$"
    if isinstance(match, AllowlistMatch):
        alternatives = [rf"{_escaped_path(path)}(/.*)?" for path in match.prefix]
        alternatives.extend(_escaped_path(path) for path in match.exact)
        if alternatives == [""]:
            return r"^/$"
        if "" in alternatives:
            return rf"^/(?:{'|'.join(alternatives)})$"
        return rf"^/({'|'.join(alternatives)})$"
    raise ValueError(f"unknown match: {match!r}")


def render_cloudflare(contract: object) -> str:
    from scripts.ingress_render import render_cloudflare as render

    return render(validate_contract(contract))


def _write_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write generated configs")
    parser.add_argument(
        "--check", action="store_true", help="fail when generated configs are stale"
    )
    args = parser.parse_args()
    if args.write == args.check:
        parser.error("choose exactly one of --write or --check")
    contract = load_contract()
    from scripts.ingress_render import output_contents as render_outputs

    outputs = render_outputs(contract)
    if args.check:
        stale = [
            str(path.relative_to(ROOT))
            for path, content in outputs
            if not path.exists() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print("stale generated ingress output: " + ", ".join(stale))
            return 1
        return 0
    for path, content in outputs:
        _write_atomic(path, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
