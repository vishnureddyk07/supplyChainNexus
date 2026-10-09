import os
import json
import random
import time
from datetime import datetime, timezone
from typing import Iterable

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
EVENT_INTERVAL = int(os.getenv("EVENT_INTERVAL", "5"))
SCENARIO_MODE = os.getenv("SCENARIO_MODE", "normal")
SUPPLIERS = (
    "supplier-001",
    "supplier-002",
    "supplier-003",
)


def build_client() -> mqtt.Client:
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def generate_payload(supplier: str) -> dict[str, object]:
    if SCENARIO_MODE == "normal":
        temperature = random.uniform(20, 30)
        humidity = random.uniform(40, 60)
    elif SCENARIO_MODE == "warning":
        temperature = random.uniform(45, 60)
        humidity = random.uniform(70, 85)
    else:
        temperature = random.uniform(70, 90)
        humidity = random.uniform(90, 100)

    return {
        "supplierId": supplier,
        "temperature": round(temperature, 2),
        "humidity": round(humidity, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def publish_sensor_events(
    client: mqtt.Client,
    suppliers: Iterable[str],
) -> None:
    supplier_choices = tuple(suppliers)

    while True:
        supplier = random.choice(supplier_choices)
        payload = generate_payload(supplier)
        topic = f"suppliers/{supplier}/telemetry"

        client.publish(topic, json.dumps(payload))
        print(topic)
        print(payload)

        time.sleep(EVENT_INTERVAL)


def main() -> None:
    client = build_client()

    print("Connecting to MQTT broker...")
    client.connect(BROKER, PORT)
    client.loop_start()
    print("Connected!")

    try:
        publish_sensor_events(client, SUPPLIERS)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
