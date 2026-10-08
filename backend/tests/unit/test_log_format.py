import json
import logging

import pytest

from app.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    mask_email,
    request_id_var,
    user_id_var,
)


@pytest.fixture(autouse=True, scope="module")
def _logging():
    configure_logging()  # installs the record factory that adds the request context


def make_record(**extra):
    return logging.getLogger("app.test").makeRecord(
        "app.test", logging.INFO, __file__, 1, "trip_added", (), None, extra=extra
    )


def test_json_line_has_context_and_extras():
    rid, uid = request_id_var.set("req-123456"), user_id_var.set(7)
    try:
        # the record factory installed by configure_logging adds the context
        record = logging.getLogRecordFactory()("app.test", logging.INFO, __file__, 1, "trip_added", (), None)
        record.trip_id = "t1"
    finally:
        request_id_var.reset(rid)
        user_id_var.reset(uid)
    entry = json.loads(JsonFormatter().format(record))
    assert entry["message"] == "trip_added"
    assert entry["level"] == "INFO"
    assert (entry["request_id"], entry["user_id"], entry["trip_id"]) == ("req-123456", 7, "t1")
    assert entry["ts"].endswith("+00:00")


def test_values_json_cannot_encode_become_strings():
    from datetime import date
    from decimal import Decimal

    entry = json.loads(JsonFormatter().format(make_record(day=date(2026, 10, 1), pct=Decimal("12.5"))))
    assert (entry["day"], entry["pct"]) == ("2026-10-01", "12.5")


def test_console_line_is_readable():
    line = ConsoleFormatter().format(make_record(shift_id=3))
    assert "INFO" in line and "trip_added" in line and "shift_id=3" in line


def test_mask_email():
    assert mask_email("driver@example.com") == "d***@example.com"
    assert mask_email("not-an-email") == "***"
