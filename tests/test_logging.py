import json
import logging

from supplychain_nexus.logging_config import StructuredLogFormatter, configure_logging


def test_structured_formatter_includes_context_fields() -> None:
    record = logging.LogRecord(
        name="pipeline",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="event persisted",
        args=(),
        exc_info=None,
    )
    record.event_id = "event-123"
    record.source_system = "sensor_simulator"

    entry = json.loads(StructuredLogFormatter().format(record))
    assert entry["message"] == "event persisted"
    assert entry["event_id"] == "event-123"
    assert entry["source_system"] == "sensor_simulator"
    assert entry["level"] == "INFO"


def test_invalid_logging_level_is_reported() -> None:
    try:
        configure_logging("not-a-level")
    except ValueError as exc:
        assert "invalid log level" in str(exc)
    else:
        raise AssertionError("invalid logging level was accepted")
