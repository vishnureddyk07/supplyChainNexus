from __future__ import annotations

import json

from supplychain_nexus.contracts import SupplyChainEvent, normalize_event_payload


def parse_mqtt_event(topic: str, payload: bytes) -> SupplyChainEvent:
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "suppliers" or not parts[1]:
        raise ValueError(f"unexpected MQTT topic: {topic}")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"payload is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("payload must be a JSON object")

    channel = parts[2]
    source = {"telemetry": "sensor_simulator", "events": "supplier_erp"}.get(channel)
    if source is None:
        raise ValueError(f"unsupported MQTT channel: {channel}")

    event = normalize_event_payload(decoded, source_system=source)
    if event.source_system != source:
        raise ValueError(
            f"event source_system ({event.source_system}) does not match MQTT channel ({channel})"
        )
    if (channel == "telemetry") != (event.event_type == "sensor.telemetry"):
        raise ValueError(f"event_type ({event.event_type}) does not match MQTT channel ({channel})")
    if event.supplier_id != parts[1]:
        raise ValueError(
            f"supplier_id in event ({event.supplier_id}) does not match topic ({parts[1]})"
        )
    return event
