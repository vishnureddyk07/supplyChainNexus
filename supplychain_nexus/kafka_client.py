from __future__ import annotations

import logging
import os
import time

from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


def create_kafka_producer() -> KafkaProducer:
    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    timeout = int(os.getenv("KAFKA_STARTUP_TIMEOUT_SECONDS", "120"))
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        producer: KafkaProducer | None = None
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                acks="all",
                retries=5,
                retry_backoff_ms=500,
                max_in_flight_requests_per_connection=1,
                request_timeout_ms=10000,
                api_version_auto_timeout_ms=5000,
            )
            if producer.bootstrap_connected():
                logger.info("connected to Kafka", extra={"bootstrap_servers": bootstrap_servers})
                return producer
            last_error = RuntimeError("Kafka bootstrap connection is not ready")
        except KafkaError as exc:
            last_error = exc
        if producer is not None:
            producer.close(timeout=1)
        time.sleep(2)

    raise RuntimeError(
        f"Kafka did not become ready within {timeout} seconds"
    ) from last_error
