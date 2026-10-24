from __future__ import annotations

import logging
import os
import time

import paho.mqtt.client as mqtt

from supplychain_nexus.contracts import SupplyChainEvent, event_to_json_bytes

logger = logging.getLogger(__name__)


def publish_supplier_event(event: SupplyChainEvent) -> None:
    broker = os.getenv("MQTT_BROKER", "mosquitto")
    port = int(os.getenv("MQTT_PORT", "1883"))
    attempts = int(os.getenv("MQTT_PUBLISH_ATTEMPTS", "3"))
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        try:
            client.connect(broker, port, keepalive=30)
            client.loop_start()
            topic = f"suppliers/{event.supplier_id}/events"
            result = client.publish(topic, event_to_json_bytes(event), qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish returned error code {result.rc}")
            result.wait_for_publish(timeout=10)
            if not result.is_published():
                raise RuntimeError("MQTT event delivery was not acknowledged")
            logger.info(
                "supplier event published",
                extra={"event_id": str(event.event_id), "topic": topic},
            )
            return
        except (OSError, RuntimeError) as exc:
            last_error = exc
            logger.warning(
                "supplier event publish attempt failed",
                extra={"attempt": attempt, "error": str(exc)},
            )
            if attempt < attempts:
                time.sleep(min(attempt, 3))
        finally:
            client.disconnect()
            client.loop_stop()

    raise RuntimeError(f"could not publish supplier event to MQTT broker {broker}:{port}") from last_error
