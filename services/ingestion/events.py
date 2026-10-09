"""Validated event envelope shared by every ingestion source."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

TOPICS = {
    "shipping": "raw.shipping",
    "weather": "raw.weather",
    "supplier_erp": "raw.supplier_erp",
    "iot": "raw.iot",
    "geopolitical": "raw.geopolitical",
}
DLQ_TOPIC = "raw.dlq"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IngestionEvent:
    source: str
    event_type: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=utc_now)
    ingested_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.source not in TOPICS:
            raise ValueError(f"Unsupported event source: {self.source}")
        if not self.event_type.strip():
            raise ValueError("event_type must not be empty")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dictionary")

    @property
    def topic(self) -> str:
        return TOPICS[self.source]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
