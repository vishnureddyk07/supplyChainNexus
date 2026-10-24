from types import SimpleNamespace

import pytest

from services.ingestion import app as ingestion_app
from services.ingestion.app import on_message
from services.ingestion.event_handler import parse_mqtt_event
from supplychain_nexus.contracts import event_to_json_bytes


def test_parse_sensor_event_from_mqtt_topic(sensor_event) -> None:
    event = parse_mqtt_event(
        f"suppliers/{sensor_event.supplier_id}/telemetry",
        event_to_json_bytes(sensor_event),
    )
    assert event == sensor_event


def test_topic_supplier_mismatch_is_rejected(sensor_event) -> None:
    with pytest.raises(ValueError, match="does not match topic"):
        parse_mqtt_event(
            "suppliers/supplier-999/telemetry",
            event_to_json_bytes(sensor_event),
        )


def test_invalid_utf8_json_is_rejected() -> None:
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        parse_mqtt_event("suppliers/supplier-001/telemetry", b"\xff")


def test_topic_channel_must_match_contract(sensor_event) -> None:
    with pytest.raises(ValueError, match="does not match MQTT channel"):
        parse_mqtt_event(
            f"suppliers/{sensor_event.supplier_id}/events",
            event_to_json_bytes(sensor_event),
        )


class RecordingProducer:
    def __init__(self, fail: bool = False) -> None:
        self.events = []
        self.dead_letters = []
        self.fail = fail

    def send_event(self, event) -> None:
        if self.fail:
            raise RuntimeError("Kafka unavailable")
        self.events.append(event)

    def send_dead_letter(self, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("Kafka unavailable")
        self.dead_letters.append(kwargs)


class RecordingMqttClient:
    def __init__(self, result: int = 0) -> None:
        self.acks = []
        self.result = result

    def ack(self, mid: int, qos: int) -> int:
        self.acks.append((mid, qos))
        return self.result


def test_mqtt_message_acknowledged_after_kafka_publish(sensor_event) -> None:
    producer = RecordingProducer()
    client = RecordingMqttClient()
    message = SimpleNamespace(
        topic=f"suppliers/{sensor_event.supplier_id}/telemetry",
        payload=event_to_json_bytes(sensor_event),
        qos=1,
        mid=8,
    )
    on_message(client, producer, message)
    assert producer.events == [sensor_event]
    assert client.acks == [(8, 1)]


def test_invalid_mqtt_payload_is_dead_lettered_and_acknowledged() -> None:
    producer = RecordingProducer()
    client = RecordingMqttClient()
    message = SimpleNamespace(
        topic="suppliers/supplier-001/telemetry",
        payload=b"{broken",
        qos=1,
        mid=9,
    )
    on_message(client, producer, message)
    assert len(producer.dead_letters) == 1
    assert client.acks == [(9, 1)]


def test_mqtt_delivery_is_not_acknowledged_if_kafka_fails(sensor_event) -> None:
    producer = RecordingProducer(fail=True)
    client = RecordingMqttClient()
    message = SimpleNamespace(
        topic=f"suppliers/{sensor_event.supplier_id}/telemetry",
        payload=event_to_json_bytes(sensor_event),
        qos=1,
        mid=10,
    )
    on_message(client, producer, message)
    assert client.acks == []


def test_ingestion_health_tracks_successful_mqtt_subscription(tmp_path, monkeypatch) -> None:
    ready_file = tmp_path / "ingestion-ready"
    monkeypatch.setattr(ingestion_app, "READY_FILE", ready_file)

    class AcceptedReasonCode:
        is_failure = False

    ingestion_app.on_subscribe(None, None, 1, [AcceptedReasonCode()], None)
    assert ready_file.is_file()

    ingestion_app.on_disconnect(None, None, None, AcceptedReasonCode(), None)
    assert not ready_file.exists()
