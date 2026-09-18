from __future__ import annotations

from wren_common.reporting import ReportCategory, classify_exception, is_reportable


def test_status_below_500_is_an_expected_report() -> None:
    class NotFound(Exception):
        status = 404

    exception = NotFound()
    assert classify_exception(exception) is ReportCategory.EXPECTED
    assert is_reportable(exception) is False


def test_status_500_and_untyped_errors_are_reportable() -> None:
    class ServerFailure(Exception):
        status = 500

    assert classify_exception(ServerFailure()) is ReportCategory.UNEXPECTED
    assert is_reportable(RuntimeError("database unavailable")) is True
