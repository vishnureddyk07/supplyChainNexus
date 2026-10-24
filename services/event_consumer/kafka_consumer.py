from __future__ import annotations

import logging
import os
import time
import base64
import json

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from kafka.structs import TopicPartition
from neo4j.exceptions import DriverError
import psycopg
from pydantic import ValidationError

from services.event_consumer.event_store import EventStore
from services.graph.service import SupplyChainGraph
from supplychain_nexus.contracts import SupplyChainEvent, event_from_json_bytes
from supplychain_nexus.topics import EVENTS_DEAD_LETTER_TOPIC, EVENTS_TOPIC

logger = logging.getLogger(__name__)


class DeadLetterPublisher:
    def __init__(self, producer: KafkaProducer) -> None:
        self._producer = producer

    def publish(self, record, error: Exception) -> None:
        source = f"kafka:{record.topic}:{record.partition}:{record.offset}"
        value = record.value
        if isinstance(value, bytes):
            raw_payload = value
        elif value is None:
            raw_payload = b""
        else:
            raw_payload = str(value).encode("utf-8", errors="replace")
        envelope = {
            "source": source,
            "reason": str(error),
            "payload_base64": base64.b64encode(raw_payload).decode("ascii"),
            "payload_is_null": value is None,
        }
        try:
            self._producer.send(
                EVENTS_DEAD_LETTER_TOPIC,
                key=record.key,
                value=json.dumps(envelope, sort_keys=True).encode("utf-8"),
            ).get(timeout=30)
        except (KafkaError, TimeoutError) as exc:
            logger.exception("failed to publish malformed Kafka record to dead-letter topic")
            raise RuntimeError("dead-letter publish failed") from exc


def decode_record(record) -> SupplyChainEvent:
    if not isinstance(record.value, bytes):
        raise ValueError("Kafka event value must be bytes")
    return event_from_json_bytes(record.value)


class EventConsumer:
    def __init__(
        self,
        consumer: KafkaConsumer,
        store: EventStore,
        dead_letters: DeadLetterPublisher,
        graph: SupplyChainGraph | None = None,
        retry_delay_seconds: float = 2,
        supplier_id_prefix: str | None = None,
    ) -> None:
        self._consumer = consumer
        self._store = store
        self._dead_letters = dead_letters
        self._graph = graph
        self._retry_delay = retry_delay_seconds
        self._supplier_id_prefix = supplier_id_prefix

    def run(self) -> None:
        self._consumer.subscribe([EVENTS_TOPIC])
        logger.info("subscribed to Kafka topic", extra={"topic": EVENTS_TOPIC})
        while True:
            try:
                records = self._consumer.poll(timeout_ms=1000, max_records=100)
            except (KafkaError, OSError):
                logger.exception("Kafka poll failed; retrying")
                time.sleep(self._retry_delay)
                continue
            if not records:
                continue
            batch = [
                record
                for partition_records in records.values()
                for record in partition_records
            ]
            try:
                for record in batch:
                    self.process_record(record)
                self._consumer.commit()
            except (
                psycopg.Error,
                KafkaError,
                DriverError,
                RuntimeError,
                TimeoutError,
                OSError,
            ):
                logger.exception("event batch failed; records will be retried")
                earliest_by_partition: dict[TopicPartition, int] = {}
                for record in batch:
                    partition = TopicPartition(record.topic, record.partition)
                    earliest_by_partition[partition] = min(
                        record.offset,
                        earliest_by_partition.get(partition, record.offset),
                    )
                for partition, offset in earliest_by_partition.items():
                    self._consumer.seek(partition, offset)
                time.sleep(self._retry_delay)

    def process_record(self, record) -> None:
        if self._supplier_id_prefix is not None and (
            not isinstance(record.key, bytes)
            or not record.key.decode("utf-8", errors="replace").startswith(
                self._supplier_id_prefix
            )
        ):
            logger.info(
                "Kafka event excluded by supplier prefix filter",
                extra={
                    "topic": record.topic,
                    "offset": record.offset,
                    "supplier_id_prefix": self._supplier_id_prefix,
                },
            )
            return
        try:
            event = decode_record(record)
        except (ValueError, ValidationError, RecursionError) as exc:
            self._dead_letters.publish(record, exc)
            logger.warning(
                "malformed Kafka event sent to dead-letter topic",
                extra={"topic": record.topic, "offset": record.offset},
            )
            return
        inserted = self._store.persist(event)
        if self._graph is not None:
            self._graph.upsert_event(event)
            self._store.mark_graph_projected(event.event_id)
        logger.info(
            "Kafka event processed",
            extra={
                "event_id": str(event.event_id),
                "inserted": inserted,
                "offset": record.offset,
            },
        )


def create_kafka_consumer() -> KafkaConsumer:
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    timeout = int(os.getenv("KAFKA_STARTUP_TIMEOUT_SECONDS", "120"))
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        consumer: KafkaConsumer | None = None
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=bootstrap_servers,
                group_id=os.getenv("KAFKA_CONSUMER_GROUP", "supplychain-postgres-v1"),
                enable_auto_commit=False,
                auto_offset_reset="earliest",
                max_poll_records=100,
                request_timeout_ms=30000,
                api_version_auto_timeout_ms=5000,
            )
            if consumer.bootstrap_connected():
                return consumer
            last_error = RuntimeError("Kafka bootstrap connection is not ready")
        except KafkaError as exc:
            last_error = exc
        if consumer is not None:
            consumer.close()
        time.sleep(2)
    raise RuntimeError(
        f"Kafka did not become ready within {timeout} seconds"
    ) from last_error
