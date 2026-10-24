from __future__ import annotations

import logging
import os
import random
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from supplychain_nexus.contracts import (
    SCHEMA_VERSION,
    SupplyChainEvent,
    event_to_json_bytes,
)
from supplychain_nexus.logging_config import configure_logging

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BROKER = os.getenv("MQTT_BROKER", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
EVENT_INTERVAL = max(1, int(os.getenv("EVENT_INTERVAL", "5")))
SCENARIO_MODE = os.getenv("SCENARIO_MODE", "normal")


def generate_sensor_event(supplier_id: str, scenario: str) -> SupplyChainEvent:
    if scenario == "normal":
        temperature = random.uniform(20, 30)
        humidity = random.uniform(40, 60)
    elif scenario == "warning":
        temperature = random.uniform(45, 60)
        humidity = random.uniform(70, 85)
    else:
        temperature = random.uniform(70, 90)
        humidity = random.uniform(90, 100)

    return SupplyChainEvent(
        schema_version=SCHEMA_VERSION,
        event_type="sensor.telemetry",
        timestamp=datetime.now(UTC),
        supplier_id=supplier_id,
        source_system="sensor_simulator",
        sensor_measurements={
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
        },
        traceability={"simulated": True},
    )


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor-simulator")
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    while True:
        try:
            client.connect(BROKER, PORT, keepalive=60)
            break
        except OSError:
            logger.exception("could not connect to MQTT broker; retrying")
            time.sleep(2)

    client.loop_start()
    logger.info("connected to MQTT broker", extra={"broker": BROKER, "port": PORT})
    suppliers = ["supplier-001", "supplier-002", "supplier-003"]
    try:
        while True:
            supplier_id = random.choice(suppliers)
            event = generate_sensor_event(supplier_id, SCENARIO_MODE)
            topic = f"suppliers/{supplier_id}/telemetry"
            info = client.publish(topic, event_to_json_bytes(event), qos=1)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(
                    "sensor event was not queued for MQTT delivery",
                    extra={"event_id": str(event.event_id), "result": info.rc},
                )
            else:
                try:
                    info.wait_for_publish(timeout=10)
                except RuntimeError:
                    logger.exception(
                        "sensor event MQTT delivery timed out",
                        extra={"event_id": str(event.event_id)},
                    )
                if info.is_published():
                    logger.info(
                        "sensor event published",
                        extra={"event_id": str(event.event_id), "topic": topic},
                    )
            time.sleep(EVENT_INTERVAL)
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
