"""Capture structlog output regardless of the process-wide filtering level.

The MCP app configures a filtering bound logger at ``critical`` for tests
(:mod:`mcp_harness` / :mod:`conftest`), which would drop the ``info``/``warning``
correlation lines before structlog's ``capture_logs`` can see them. This
temporarily installs a permissive wrapper so the real processor chain
(``merge_contextvars``) still runs and the lines are captured, then restores the
configured wrapper on exit.

Callers still reset the module ``_log`` under test to a fresh
``structlog.get_logger()`` inside the block: the module-level loggers cache a
filtered bound logger on first use, so a fresh proxy is needed to pick up the
permissive wrapper installed here.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

if TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping


@contextmanager
def capture_correlated_logs() -> Iterator[list[MutableMapping[str, Any]]]:
    """Yield captured log entries with ``merge_contextvars`` applied, bypassing
    the process-wide ``critical`` level filter for the duration of the block."""
    old_wrapper = structlog.get_config()["wrapper_class"]
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG))
    try:
        with capture_logs(processors=[merge_contextvars]) as logs:
            yield logs
    finally:
        structlog.configure(wrapper_class=old_wrapper)
