from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import paho.mqtt.client as mqtt
import psycopg
import pytest
from neo4j import GraphDatabase

from supplychain_nexus.contracts import SupplyChainEvent, event_to_json_bytes
from tests.sensor_simulator_imports import generate_sensor_event

RUN_INTEGRATION = os.getenv("RUN_PIPELINE_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="set RUN_PIPELINE_INTEGRATION=1 with the local Compose stack running",
)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
ERP_URL = os.getenv("ERP_URL", "http://localhost:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/supplychain",
)


NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


@pytest.fixture(scope="session", autouse=True)
def wait_for_pipeline_database() -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
                migrated = connection.execute(
                    "SELECT to_regclass('public.supply_chain_events')"
                ).fetchone()[0]
            if migrated is not None:
                return
        except psycopg.OperationalError:
            pass
        time.sleep(1)
    raise AssertionError("PostgreSQL and the Flyway event migration did not become ready")


def _publish(event: SupplyChainEvent, channel: str) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    try:
        topic = f"suppliers/{event.supplier_id}/{channel}"
        message = event_to_json_bytes(event)
        for _ in range(2):
            result = client.publish(topic, message, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise AssertionError(f"MQTT publish failed with code {result.rc}")
            result.wait_for_publish(timeout=10)
            if not result.is_published():
                raise AssertionError(f"MQTT publish was not acknowledged: {topic}")
    finally:
        client.disconnect()
        client.loop_stop()


def _wait_for_persisted_event(event_id: str) -> int:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
            count = connection.execute(
                "SELECT count(*) FROM supply_chain_events WHERE event_id = %s",
                (event_id,),
            ).fetchone()[0]
        if count:
            return count
        time.sleep(1)
    raise AssertionError(f"event {event_id} was not persisted within 45 seconds")


def _wait_for_graph_event(event_id: str) -> int:
    deadline = time.monotonic() + 45
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        driver.verify_connectivity()
        while time.monotonic() < deadline:
            with driver.session() as session:
                count = session.run(
                    """
                    MATCH (:Supplier)-[:HAS_EVENT]->(event:SupplyChainEvent {event_id: $event_id})
                    RETURN count(event) AS event_count
                    """,
                    event_id=event_id,
                ).single()["event_count"]
            if count:
                return count
            time.sleep(1)
    raise AssertionError(f"event {event_id} was not projected to Neo4j within 45 seconds")


def test_running_sensor_simulator_reaches_postgres() -> None:
    with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
        started_after = connection.execute(
            "SELECT MAX(received_at) "
            "FROM supply_chain_events WHERE source_system = 'sensor_simulator'"
        ).fetchone()[0]
    if started_after is None:
        started_after = datetime.now(UTC) - timedelta(seconds=1)

    deadline = time.monotonic() + 45
    event_payload = None
    while time.monotonic() < deadline:
        with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
            record = connection.execute(
                """
                SELECT payload
                FROM supply_chain_events
                WHERE source_system = 'sensor_simulator' AND received_at > %s
                ORDER BY received_at
                LIMIT 1
                """,
                (started_after,),
            ).fetchone()
        if record:
            event_payload = record[0]
            break
        time.sleep(1)

    assert event_payload is not None, "running sensor simulator produced no persisted event"
    event = SupplyChainEvent.model_validate(event_payload)
    assert event.source_system == "sensor_simulator"
    assert event.event_type == "sensor.telemetry"
    assert _wait_for_graph_event(str(event.event_id)) == 1


def test_erp_event_reaches_postgres_once() -> None:
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{ERP_URL}/supplier-event",
                timeout=15,
            ) as response:
                event = SupplyChainEvent.model_validate(json.load(response))
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 503:
                raise
            last_error = exc
        except urllib.error.URLError as exc:
            last_error = exc
        time.sleep(1)
    else:
        raise AssertionError("supplier ERP mock did not become ready") from last_error
    assert event.source_system == "supplier_erp"
    assert _wait_for_persisted_event(str(event.event_id)) == 1
    assert _wait_for_graph_event(str(event.event_id)) == 1
    with psycopg.connect(DATABASE_URL, connect_timeout=5) as connection:
        supplier = connection.execute(
            "SELECT 1 FROM suppliers WHERE external_id = %s",
            (event.supplier_id,),
        ).fetchone()
    assert supplier is not None


def test_duplicate_mqtt_delivery_does_not_duplicate_database_event() -> None:
    event = generate_sensor_event("sensor-duplicate-" + str(uuid4()), "warning")
    _publish(event, "telemetry")
    assert _wait_for_persisted_event(str(event.event_id)) == 1
    assert _wait_for_graph_event(str(event.event_id)) == 1
