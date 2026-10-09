import asyncio

from services.graph.postgres_repository import PostgresEventRepository
from services.ingestion.events import IngestionEvent
from services.ingestion.publisher import InMemoryEventPublisher
from services.ingestion.schema_validation import SchemaValidationError


def test_supplier_alias_is_normalized_before_validation():
    event = IngestionEvent(
        source="iot",
        event_type="sensor_telemetry",
        payload={"supplierId": "  SUPPLIER-001 ", "temperature": 22.0, "humidity": 50.0, "timestamp": "2026-01-01T00:00:00+00:00"},
    )
    assert event.payload["supplier_id"] == "supplier-001"
    assert "supplierId" not in event.payload


def test_malformed_supplier_event_is_routed_to_dlq():
    async def run():
        publisher = InMemoryEventPublisher()
        event = IngestionEvent(source="supplier_erp", event_type="supplier_event", payload={})
        await publisher.publish(event)
        assert not publisher.events
        assert publisher.dlq_events[0]["event_id"] == event.event_id

    asyncio.run(run())


def test_duplicate_event_id_is_not_published_twice():
    async def run():
        publisher = InMemoryEventPublisher()
        event = IngestionEvent(source="iot", event_type="sensor_telemetry", payload={"temperature": 20.0})
        await publisher.publish(event)
        await publisher.publish(event)
        assert len(publisher.events) == 1

    asyncio.run(run())


def test_postgres_repository_rejects_malformed_event_without_pool_access():
    async def run():
        repository = PostgresEventRepository(None)
        try:
            await repository.persist({"event_id": "bad", "payload": []})
        except ValueError as error:
            assert "object payload" in str(error)
        else:
            raise AssertionError("malformed event was accepted")

    asyncio.run(run())
