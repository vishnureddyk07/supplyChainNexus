from __future__ import annotations

import logging
import os
import time

import psycopg

from services.event_consumer.event_store import EventStore
from services.event_consumer.kafka_consumer import (
    DeadLetterPublisher,
    EventConsumer,
    create_kafka_consumer,
)
from services.graph.service import SupplyChainGraph
from supplychain_nexus.kafka_client import create_kafka_producer
from supplychain_nexus.logging_config import configure_logging

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def wait_for_postgres(dsn: str, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=5):
                logger.info("connected to PostgreSQL")
                return
        except psycopg.OperationalError:
            logger.warning("PostgreSQL is not ready; retrying")
            time.sleep(2)
    raise RuntimeError(f"PostgreSQL did not become ready within {timeout_seconds} seconds")


def main() -> None:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@postgres:5432/supplychain",
    )
    timeout = int(os.getenv("DEPENDENCY_STARTUP_TIMEOUT_SECONDS", "120"))
    wait_for_postgres(dsn, timeout)
    store = EventStore(dsn)
    graph = SupplyChainGraph.from_env()
    for event in store.unprojected_graph_events():
        graph.upsert_event(event)
        store.mark_graph_projected(event.event_id)
        logger.info(
            "historical event projected to Neo4j",
            extra={"event_id": str(event.event_id)},
        )
    consumer = create_kafka_consumer()
    producer = create_kafka_producer()
    service = EventConsumer(
        consumer,
        store,
        DeadLetterPublisher(producer),
        graph=graph,
        supplier_id_prefix=os.getenv("KAFKA_SUPPLIER_ID_PREFIX"),
    )
    try:
        service.run()
    finally:
        consumer.close()
        producer.flush(timeout=30)
        producer.close(timeout=30)
        graph.close()


if __name__ == "__main__":
    main()
