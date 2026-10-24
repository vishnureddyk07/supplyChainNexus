from __future__ import annotations

from neo4j.time import DateTime

from services.graph.service import SupplyChainGraph, _graph_value


class Result:
    def consume(self) -> None:
        return None


class Transaction:
    def __init__(self) -> None:
        self.queries = []

    def run(self, query, **parameters) -> Result:
        self.queries.append((query, parameters))
        return Result()


class Session:
    def __init__(self, transaction: Transaction) -> None:
        self.transaction = transaction

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute_write(self, callback, *args) -> None:
        callback(self.transaction, *args)


class Driver:
    def __init__(self, transaction: Transaction) -> None:
        self.transaction = transaction

    def session(self) -> Session:
        return Session(self.transaction)


def test_event_projection_uses_idempotent_merge_and_only_known_facts(sensor_event) -> None:
    transaction = Transaction()
    graph = SupplyChainGraph(Driver(transaction))

    graph.upsert_event(sensor_event)

    assert len(transaction.queries) == 2
    event_query, event_parameters = transaction.queries[0]
    telemetry_query, telemetry_parameters = transaction.queries[1]
    assert "MERGE (supplier:Supplier" in event_query
    assert "MERGE (event:SupplyChainEvent" in event_query
    assert "MERGE (supplier)-[:HAS_EVENT]->(event)" in event_query
    assert event_parameters["event_id"] == str(sensor_event.event_id)
    assert telemetry_parameters["temperature"] == sensor_event.sensor_measurements.temperature
    assert "ASSOCIATED_WITH" not in telemetry_query
    assert len([query for query, _ in transaction.queries if "SUPPLIES" in query]) == 0


def test_graph_temporal_properties_are_json_serializable() -> None:
    timestamp = DateTime(2026, 10, 24, 8, 0, 0)

    assert _graph_value({"created_at": timestamp}) == {
        "created_at": timestamp.isoformat()
    }
