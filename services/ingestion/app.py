from __future__ import annotations

import logging
import os
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode
from pydantic import ValidationError

from services.ingestion.event_handler import parse_mqtt_event
from services.ingestion.kafka_producer import EventProducer, create_event_producer
from supplychain_nexus.logging_config import configure_logging

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
READY_FILE = Path(os.getenv("INGESTION_READY_FILE", "/tmp/ingestion-ready"))


def on_connect(
    client: mqtt.Client,
    producer: EventProducer,
    flags: mqtt.ConnectFlags,
    reason_code: ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    if reason_code.is_failure:
        logger.error("MQTT connection rejected", extra={"reason": str(reason_code)})
        return
    result, _ = client.subscribe("suppliers/+/+", qos=1)
    if result != mqtt.MQTT_ERR_SUCCESS:
        logger.error("could not subscribe to supplier event topics", extra={"result": result})
        return
    logger.info("subscribed to suppliers/+/+")


def on_subscribe(
    client: mqtt.Client,
    producer: EventProducer,
    mid: int,
    reason_codes: list[ReasonCode],
    properties: mqtt.Properties | None,
) -> None:
    if any(reason_code.is_failure for reason_code in reason_codes):
        logger.error("MQTT broker rejected the supplier event subscription")
        return
    try:
        READY_FILE.parent.mkdir(parents=True, exist_ok=True)
        READY_FILE.touch()
    except OSError:
        logger.exception("could not record MQTT subscription readiness")
        return
    logger.info("MQTT subscription is ready")


def on_disconnect(
    client: mqtt.Client,
    producer: EventProducer,
    disconnect_flags: mqtt.DisconnectFlags,
    reason_code: ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    try:
        READY_FILE.unlink(missing_ok=True)
    except OSError:
        logger.exception("could not clear MQTT subscription readiness")
    logger.warning("disconnected from MQTT broker", extra={"reason": str(reason_code)})


def on_message(
    client: mqtt.Client,
    producer: EventProducer,
    message: mqtt.MQTTMessage,
) -> None:
    try:
        event = parse_mqtt_event(message.topic, message.payload)
    except (ValueError, ValidationError, RecursionError) as exc:
        logger.warning(
            "invalid MQTT event",
            extra={"topic": message.topic, "error": str(exc)},
        )
        try:
            producer.send_dead_letter(
                payload=message.payload,
                reason=str(exc),
                source=f"mqtt:{message.topic}",
            )
        except RuntimeError:
            logger.exception("could not forward invalid MQTT event; leaving unacknowledged")
            return
    else:
        try:
            producer.send_event(event)
        except RuntimeError:
            logger.exception(
                "could not forward MQTT event; leaving unacknowledged",
                extra={"event_id": str(event.event_id)},
            )
            return

    if message.qos > 0:
        result = client.ack(message.mid, message.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error("MQTT acknowledgement failed", extra={"mid": message.mid})


def main() -> None:
    broker = os.getenv("MQTT_BROKER", "mosquitto")
    port = int(os.getenv("MQTT_PORT", "1883"))
    producer = create_event_producer()
    READY_FILE.unlink(missing_ok=True)
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="supplychain-ingestion",
        clean_session=False,
        manual_ack=True,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.user_data_set(producer)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    logger.info("connecting to MQTT broker", extra={"broker": broker, "port": port})
    try:
        client.connect_async(broker, port, keepalive=60)
        client.loop_forever(retry_first_connection=True)
    finally:
        client.disconnect()
        producer.close()


if __name__ == "__main__":
    main()
