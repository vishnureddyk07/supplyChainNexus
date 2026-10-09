import asyncio

from services.ingestion.connectors import (
    GdeltConnector,
    MarineTrafficConnector,
    MqttIotConnector,
    OpenWeatherConnector,
    SupplierErpConnector,
)
from services.ingestion.publisher import InMemoryEventPublisher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    async def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return FakeResponse(self.payload)


def test_http_connectors_publish_standard_events():
    async def run():
        cases = [
            (MarineTrafficConnector, {"data": [{"mmsi": "1"}]}, {"api_key": "key"}, "raw.shipping"),
            (OpenWeatherConnector, {"name": "Rotterdam"}, {"api_key": "key", "locations": [{"lat": 1, "lon": 2}]}, "raw.weather"),
            (GdeltConnector, {"articles": [{"title": "port"}]}, {}, "raw.geopolitical"),
            (SupplierErpConnector, [{"supplier_id": "supplier-1"}], {}, "raw.supplier_erp"),
        ]
        for connector_type, response, options, expected_topic in cases:
            publisher = InMemoryEventPublisher()
            connector = connector_type(publisher, client=FakeClient(response), **options)
            assert await connector.poll_once() == 1
            assert len(publisher.events) == 1
            assert publisher.events[0].topic == expected_topic
            await connector.close()

    asyncio.run(run())


def test_mqtt_payload_is_published_to_raw_iot():
    async def run():
        publisher = InMemoryEventPublisher()
        connector = MqttIotConnector(publisher)

        class Message:
            topic = "suppliers/supplier-1/telemetry"
            payload = b'{"temperature": 22.5}'

        connector.on_message(None, asyncio.get_running_loop(), Message())
        await asyncio.sleep(0)
        assert publisher.events[0].topic == "raw.iot"
        assert publisher.events[0].payload["temperature"] == 22.5

    asyncio.run(run())


def test_mqtt_invalid_payload_does_not_raise():
    async def run():
        connector = MqttIotConnector(InMemoryEventPublisher())

        class Message:
            topic = "suppliers/supplier-1/telemetry"
            payload = b"not-json"

        connector.on_message(None, asyncio.get_running_loop(), Message())

    asyncio.run(run())


def test_invalid_event_is_isolated_to_dlq_with_context():
    async def run():
        publisher = InMemoryEventPublisher()
        connector = SupplierErpConnector(
            publisher,
            client=FakeClient([{"unexpected": "value"}]),
        )
        assert await connector.poll_once() == 1
        assert publisher.events == []
        assert len(publisher.dlq_events) == 1
        dlq = publisher.dlq_events[0]
        assert dlq["source"] == "supplier_erp"
        assert dlq["error_type"] == "SchemaValidationError"
        assert dlq["timestamp"]
        await connector.close()

    asyncio.run(run())
