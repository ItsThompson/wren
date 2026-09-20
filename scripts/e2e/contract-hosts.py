#!/usr/bin/env python3
"""Read canonical E2E hostnames from the ingress contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

HOSTNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "deployments" / "ingress" / "contract.json"


def fail(message: str) -> int:
    print(f"e2e hosts: {message}", file=sys.stderr)
    return 1


def load_hosts() -> dict[str, str]:
    with CONTRACT_PATH.open(encoding="utf-8") as contract_file:
        document: Any = json.load(contract_file)

    hosts = document.get("hosts") if isinstance(document, dict) else None
    if not isinstance(hosts, list):
        raise ValueError("contract hosts must be a list")

    result: dict[str, str] = {}
    for entry in hosts:
        if not isinstance(entry, dict):
            raise ValueError("contract host entries must be objects")
        host_id = entry.get("id")
        hostname = entry.get("e2e_hostname")
        if not isinstance(host_id, str) or not host_id:
            raise ValueError("contract host ids must be non-empty strings")
        if hostname is None:
            continue
        if not isinstance(hostname, str) or not HOSTNAME_PATTERN.fullmatch(hostname):
            raise ValueError(f"invalid E2E hostname for {host_id}")
        if host_id in result or hostname in result.values():
            raise ValueError("E2E host ids and hostnames must be unique")
        result[host_id] = hostname

    if not result:
        raise ValueError("contract has no E2E hostnames")
    return result


def main(arguments: list[str]) -> int:
    if not arguments:
        return fail("pass --all or one or more host ids")
    try:
        hosts = load_hosts()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return fail(str(error))

    if arguments == ["--all"]:
        print(" ".join(hosts.values()))
        return 0

    selected: list[str] = []
    for host_id in arguments:
        hostname = hosts.get(host_id)
        if hostname is None:
            return fail(f"E2E hostname is not defined for host id {host_id}")
        selected.append(hostname)
    print(" ".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
