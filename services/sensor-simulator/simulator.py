import json
import os
import random
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_BROKER", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
EVENT_INTERVAL = int(os.getenv("EVENT_INTERVAL", "5"))
SCENARIO_MODE = os.getenv("SCENARIO_MODE", "normal")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

print("Connecting to MQTT broker...")
client.connect(BROKER, PORT)
client.loop_start()
print("Connected!")

suppliers = [
    "supplier-001",
    "supplier-002",
    "supplier-003",
]

while True:
    supplier = random.choice(suppliers)

    if SCENARIO_MODE == "normal":
        temperature = random.uniform(20, 30)
        humidity = random.uniform(40, 60)
    elif SCENARIO_MODE == "warning":
        temperature = random.uniform(45, 60)
        humidity = random.uniform(70, 85)
    else:
        temperature = random.uniform(70, 90)
        humidity = random.uniform(90, 100)

    payload = {
        "supplierId": supplier,
        "temperature": round(temperature, 2),
        "humidity": round(humidity, 2),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    topic = f"suppliers/{supplier}/telemetry"

    client.publish(topic, json.dumps(payload))

    print(topic)
    print(payload)

    time.sleep(EVENT_INTERVAL)
