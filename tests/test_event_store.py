from datetime import UTC, datetime

from services.event_consumer.event_store import EventStore
from supplychain_nexus.contracts import SupplyChainEvent


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self._fetch_result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query: str, params) -> None:
        self.connection.queries.append((query, params))
        if "INSERT INTO supply_chain_events" in query:
            self._fetch_result = object() if self.connection.inserted else None

    def fetchone(self):
        return self._fetch_result


class FakeConnection:
    def __init__(self, inserted: bool) -> None:
        self.inserted = inserted
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection_closed = True
        return False

    def cursor(self):
        return FakeCursor(self)


def _supplier_event() -> SupplyChainEvent:
    return SupplyChainEvent(
        event_type="supplier.updated",
        timestamp=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
        supplier_id="erp-123",
        source_system="supplier_erp",
        supplier_data={
            "name": "Example Supplier",
            "contact_email": "ops@example.test",
            "phone": "555-0100",
            "country": "Exampleland",
            "status": "ACTIVE",
        },
        traceability={"simulated": True},
    )


def test_event_and_supplier_are_written_in_same_transaction() -> None:
    connection = FakeConnection(inserted=True)
    store = EventStore("postgresql://unused", lambda *args, **kwargs: connection)

    assert store.persist(_supplier_event()) is True
    assert len(connection.queries) == 2
    assert "ON CONFLICT (event_id) DO NOTHING" in connection.queries[0][0]
    assert "ON CONFLICT (external_id) DO UPDATE" in connection.queries[1][0]
    assert connection.queries[1][1][2] == "example.test"
    assert connection.connection_closed


def test_duplicate_event_skips_supplier_update() -> None:
    connection = FakeConnection(inserted=False)
    store = EventStore("postgresql://unused", lambda *args, **kwargs: connection)

    assert store.persist(_supplier_event()) is False
    assert len(connection.queries) == 1
