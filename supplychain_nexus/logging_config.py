from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class StructuredLogFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()
        self._standard_fields = set(logging.makeLogRecord({}).__dict__)
        self._standard_fields.update({"asctime", "message"})

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in self._standard_fields and not key.startswith("_")
            }
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    resolved_level = logging.getLevelName(level.upper())
    if not isinstance(resolved_level, int):
        raise ValueError(f"invalid log level: {level}")
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(resolved_level)
