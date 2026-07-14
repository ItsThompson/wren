"""Logging: JSON renderer outside dev, console in dev, bound service field."""

from __future__ import annotations

import json

import structlog

from wren.core.logging import _build_processors, _renderer, get_logger


def test_non_dev_renderer_emits_json() -> None:
    render = _renderer(is_dev=False)
    rendered = render(None, "info", {"event": "boot", "service": "wren-external"})
    assert isinstance(rendered, str)
    parsed = json.loads(rendered)
    assert parsed["event"] == "boot"
    assert parsed["service"] == "wren-external"


def test_dev_renderer_is_console() -> None:
    assert isinstance(_renderer(is_dev=True), structlog.dev.ConsoleRenderer)


def test_processor_chain_ends_with_renderer() -> None:
    processors = _build_processors(is_dev=False)
    assert isinstance(processors[-1], structlog.processors.JSONRenderer)


def test_get_logger_binds_service_field() -> None:
    with structlog.testing.capture_logs() as logs:
        get_logger("wren-internal").info("event_x")
    assert logs[0]["service"] == "wren-internal"
    assert logs[0]["event"] == "event_x"
