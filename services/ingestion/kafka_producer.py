from __future__ import annotations

import json
import logging
import base64
from datetime import UTC, datetime
from kafka import KafkaProducer
from kafka.errors import KafkaError

from supplychain_nexus.contracts import SupplyChainEvent, event_to_json_bytes
from supplychain_nexus.kafka_client import create_kafka_producer
from supplychain_nexus.topics import EVENTS_DEAD_LETTER_TOPIC, EVENTS_TOPIC

logger = logging.getLogger(__name__)


class EventProducer:
    def __init__(self, producer: KafkaProducer) -> None:
        self._producer = producer

    def send_event(self, event: SupplyChainEvent) -> None:
        self._send(
            EVENTS_TOPIC,
            event_to_json_bytes(event),
            event.supplier_id.encode("utf-8"),
        )
        logger.info(
            "event published to Kafka",
            extra={"event_id": str(event.event_id), "topic": EVENTS_TOPIC},
        )

    def send_dead_letter(
        self,
        *,
        payload: bytes,
        reason: str,
        source: str,
        message_key: bytes | None = None,
    ) -> None:
        envelope = {
            "source": source,
            "reason": reason,
            "received_at": datetime.now(UTC).isoformat(),
            "payload_base64": base64.b64encode(payload).decode("ascii"),
        }
        encoded = json.dumps(envelope, sort_keys=True).encode("utf-8")
        self._send(EVENTS_DEAD_LETTER_TOPIC, encoded, message_key)
        logger.warning(
            "invalid event forwarded to Kafka dead-letter topic",
            extra={"topic": EVENTS_DEAD_LETTER_TOPIC, "source": source},
        )

    def _send(self, topic: str, payload: bytes, key: bytes | None) -> None:
        try:
            self._producer.send(topic, key=key, value=payload).get(timeout=30)
        except (KafkaError, TimeoutError) as exc:
            logger.exception("Kafka publish failed", extra={"topic": topic})
            raise RuntimeError(f"could not publish message to {topic}") from exc

    def close(self) -> None:
        self._producer.flush(timeout=30)
        self._producer.close(timeout=30)


def create_event_producer() -> EventProducer:
    return EventProducer(create_kafka_producer())
