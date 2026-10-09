"""Small dependency-free Prometheus metrics registry for the ingestion service."""

from __future__ import annotations

from collections import Counter
from threading import Lock


class IngestionMetrics:
    def __init__(self) -> None:
        self._values: Counter[str] = Counter()
        self._lock = Lock()

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._values[name] += amount

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)

    def prometheus(self) -> str:
        values = self.snapshot()
        names = (
            "ingestion_events_accepted_total",
            "ingestion_events_rejected_total",
            "ingestion_events_failed_total",
            "ingestion_events_dlq_total",
        )
        return "".join(f"# TYPE {name} counter\n{name} {values.get(name, 0)}\n" for name in names)


metrics = IngestionMetrics()
