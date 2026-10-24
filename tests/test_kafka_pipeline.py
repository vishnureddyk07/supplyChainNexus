import base64
import json

import pytest
import psycopg
from kafka.structs import TopicPartition
from neo4j.exceptions import ServiceUnavailable

from services.event_consumer.kafka_consumer import EventConsumer
from services.event_consumer.kafka_consumer import DeadLetterPublisher, decode_record
from services.ingestion.kafka_producer import EventProducer
from supplychain_nexus.contracts import event_to_json_bytes
from supplychain_nexus.topics import EVENTS_DEAD_LETTER_TOPIC, EVENTS_TOPIC


class FakeFuture:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def get(self, timeout: int) -> None:
        if self.error:
            raise self.error


class FakeKafkaProducer:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent = []
        self.error = error

    def send(self, topic, *, key, value):
        self.sent.append((topic, key, value))
        return FakeFuture(self.error)


def test_event_producer_serializes_and_keys_by_supplier(sensor_event) -> None:
    raw = FakeKafkaProducer()
    EventProducer(raw).send_event(sensor_event)
    topic, key, value = raw.sent[0]
    assert topic == EVENTS_TOPIC
    assert key == sensor_event.supplier_id.encode("utf-8")
    assert json.loads(value) == json.loads(event_to_json_bytes(sensor_event))


def test_event_producer_surfaces_kafka_delivery_failure(sensor_event) -> None:
    raw = FakeKafkaProducer(TimeoutError("timed out"))
    with pytest.raises(RuntimeError, match="could not publish"):
        EventProducer(raw).send_event(sensor_event)


def test_dead_letter_payload_is_preserved() -> None:
    raw = FakeKafkaProducer()
    invalid = b"\xffinvalid"
    DeadLetterPublisher(raw).publish(
        type(
            "Record",
            (),
            {
                "topic": EVENTS_TOPIC,
                "partition": 1,
                "offset": 12,
                "key": b"supplier-1",
                "value": invalid,
            },
        )(),
        ValueError("invalid JSON"),
    )
    topic, key, value = raw.sent[0]
    envelope = json.loads(value)
    assert topic == EVENTS_DEAD_LETTER_TOPIC
    assert key == b"supplier-1"
    assert base64.b64decode(envelope["payload_base64"]) == invalid
    assert envelope["source"] == f"kafka:{EVENTS_TOPIC}:1:12"


def test_consumer_rejects_non_byte_kafka_payload() -> None:
    record = type("Record", (), {"value": None})()
    with pytest.raises(ValueError, match="must be bytes"):
        decode_record(record)


def test_consumer_supplier_prefix_filter_prevents_cross_environment_persistence(
    sensor_event,
) -> None:
    class Store:
        persisted = 0

        def persist(self, event) -> bool:
            self.persisted += 1
            return True

    store = Store()
    consumer = EventConsumer(
        type("Consumer", (), {})(),
        store,
        DeadLetterPublisher(FakeKafkaProducer()),
        supplier_id_prefix="demo-supplier-",
    )
    external_event = sensor_event.model_copy(
        update={"supplier_id": "operational-supplier-1"}
    )
    consumer.process_record(
        type(
            "Record",
            (),
            {
                "topic": EVENTS_TOPIC,
                "partition": 0,
                "offset": 1,
                "key": external_event.supplier_id.encode(),
                "value": event_to_json_bytes(external_event),
            },
        )()
    )

    assert store.persisted == 0


def test_consumer_supplier_prefix_filter_accepts_demo_events(sensor_event) -> None:
    class Store:
        persisted = 0

        def persist(self, event) -> bool:
            self.persisted += 1
            return True

    store = Store()
    consumer = EventConsumer(
        type("Consumer", (), {})(),
        store,
        DeadLetterPublisher(FakeKafkaProducer()),
        supplier_id_prefix="demo-supplier-",
    )
    demo_event = sensor_event.model_copy(
        update={"supplier_id": "demo-supplier-001"}
    )
    consumer.process_record(
        type(
            "Record",
            (),
            {
                "topic": EVENTS_TOPIC,
                "partition": 0,
                "offset": 2,
                "key": demo_event.supplier_id.encode(),
                "value": event_to_json_bytes(demo_event),
            },
        )()
    )

    assert store.persisted == 1


def test_database_failure_seeks_record_without_committing(sensor_event) -> None:
    partition = TopicPartition(EVENTS_TOPIC, 0)
    record = type(
        "Record",
        (),
        {
            "topic": EVENTS_TOPIC,
            "partition": 0,
            "offset": 17,
            "value": event_to_json_bytes(sensor_event),
        },
    )()

    class Consumer:
        def __init__(self) -> None:
            self.poll_count = 0
            self.seeks = []
            self.commits = 0

        def subscribe(self, topics) -> None:
            self.topics = topics

        def poll(self, **kwargs):
            self.poll_count += 1
            if self.poll_count == 1:
                return {partition: [record]}
            raise StopIteration

        def seek(self, topic_partition, offset) -> None:
            self.seeks.append((topic_partition, offset))

        def commit(self) -> None:
            self.commits += 1

    class BrokenStore:
        def persist(self, event) -> bool:
            raise psycopg.OperationalError("database unavailable")

    consumer = Consumer()
    service = EventConsumer(
        consumer,
        BrokenStore(),
        DeadLetterPublisher(FakeKafkaProducer()),
        retry_delay_seconds=0,
    )
    with pytest.raises(StopIteration):
        service.run()
    assert consumer.seeks == [(partition, 17)]
    assert consumer.commits == 0


def test_graph_failure_seeks_record_without_committing(sensor_event) -> None:
    partition = TopicPartition(EVENTS_TOPIC, 0)
    record = type(
        "Record",
        (),
        {
            "topic": EVENTS_TOPIC,
            "partition": 0,
            "offset": 23,
            "value": event_to_json_bytes(sensor_event),
        },
    )()

    class Consumer:
        def __init__(self) -> None:
            self.poll_count = 0
            self.seeks = []
            self.commits = 0

        def subscribe(self, topics) -> None:
            self.topics = topics

        def poll(self, **kwargs):
            self.poll_count += 1
            if self.poll_count == 1:
                return {partition: [record]}
            raise StopIteration

        def seek(self, topic_partition, offset) -> None:
            self.seeks.append((topic_partition, offset))

        def commit(self) -> None:
            self.commits += 1

    class Store:
        def __init__(self) -> None:
            self.persisted = 0
            self.projected = 0

        def persist(self, event) -> bool:
            self.persisted += 1
            return True

        def mark_graph_projected(self, event_id) -> None:
            self.projected += 1

    class BrokenGraph:
        def upsert_event(self, event) -> None:
            raise ServiceUnavailable("graph is temporarily unavailable")

    consumer = Consumer()
    store = Store()
    service = EventConsumer(
        consumer,
        store,
        DeadLetterPublisher(FakeKafkaProducer()),
        graph=BrokenGraph(),
        retry_delay_seconds=0,
    )
    with pytest.raises(StopIteration):
        service.run()
    assert consumer.seeks == [(partition, 23)]
    assert consumer.commits == 0
    assert store.persisted == 1
    assert store.projected == 0
