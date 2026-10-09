"""Kafka publishing with a small injectable interface for tests."""

from __future__ import annotations

import json
import logging
import asyncio
import os
from typing import Any, Protocol

from .events import DLQ_TOPIC, IngestionEvent, utc_now
from .metrics import metrics
from .schema_validation import AvroSchemaValidator, SchemaValidationError

LOGGER = logging.getLogger("ingestion.publisher")


class EventPublisher(Protocol):
    async def publish(self, event: IngestionEvent) -> None: ...
    async def publish_dlq(self, event: IngestionEvent, error: Exception) -> None: ...


class KafkaEventPublisher:
    def __init__(self, bootstrap_servers: str, validator: AvroSchemaValidator | None = None) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self.validator = validator or AvroSchemaValidator()

    async def start(self) -> None:
        from aiokafka import AIOKafkaProducer

        retries = int(os.getenv("KAFKA_START_RETRIES", "10"))
        delay = float(os.getenv("KAFKA_RETRY_SECONDS", "5"))
        for attempt in range(retries + 1):
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda value: json.dumps(value).encode("utf-8"),
                key_serializer=lambda value: value.encode("utf-8"),
            )
            try:
                await self._producer.start()
                LOGGER.info("kafka_publisher_started", extra={"bootstrap_servers": self.bootstrap_servers})
                return
            except Exception as exc:
                await self._producer.stop()
                self._producer = None
                if attempt >= retries:
                    LOGGER.error("kafka_publisher_start_failed", extra={"error": str(exc)})
                    raise
                LOGGER.warning("kafka_publisher_retry", extra={"attempt": attempt + 1, "delay": delay, "error": str(exc)})
                await asyncio.sleep(delay)

    async def publish(self, event: IngestionEvent) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka publisher has not been started")
        try:
            self.validator.validate(event.source, event.payload)
        except SchemaValidationError as exc:
            metrics.increment("ingestion_events_rejected_total")
            await self.publish_dlq(event, exc)
            return
        try:
            await self._producer.send_and_wait(event.topic, event.as_dict(), key=event.event_id)
        except Exception:
            metrics.increment("ingestion_events_failed_total")
            raise
        metrics.increment("ingestion_events_accepted_total")
        LOGGER.info("event_published", extra={"source": event.source, "topic": event.topic})

    async def publish_dlq(self, event: IngestionEvent, error: Exception) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka publisher has not been started")
        dlq_event = {
            "event_id": event.event_id,
            "source": event.source,
            "timestamp": utc_now(),
            "error_type": type(error).__name__,
            "error": str(error),
            "original_topic": event.topic,
            "event": event.as_dict(),
        }
        await self._producer.send_and_wait(DLQ_TOPIC, dlq_event, key=event.event_id)
        metrics.increment("ingestion_events_dlq_total")
        LOGGER.warning("event_routed_to_dlq", extra={"source": event.source, "topic": DLQ_TOPIC, "error": str(error)})

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


class InMemoryEventPublisher:
    """Useful for connector tests and local development without Kafka."""

    def __init__(self, validator: AvroSchemaValidator | None = None) -> None:
        self.events: list[IngestionEvent] = []
        self.dlq_events: list[dict[str, Any]] = []
        self.validator = validator or AvroSchemaValidator()
        self._event_ids: set[str] = set()

    async def publish(self, event: IngestionEvent) -> None:
        if event.event_id in self._event_ids:
            metrics.increment("ingestion_events_duplicates_total")
            return
        try:
            self.validator.validate(event.source, event.payload)
        except SchemaValidationError as exc:
            metrics.increment("ingestion_events_rejected_total")
            await self.publish_dlq(event, exc)
            return
        self.events.append(event)
        self._event_ids.add(event.event_id)
        metrics.increment("ingestion_events_accepted_total")

    async def publish_dlq(self, event: IngestionEvent, error: Exception) -> None:
        self.dlq_events.append({
            "event_id": event.event_id,
            "source": event.source,
            "timestamp": utc_now(),
            "error_type": type(error).__name__,
            "error": str(error),
            "original_topic": event.topic,
            "event": event.as_dict(),
        })
        metrics.increment("ingestion_events_dlq_total")
