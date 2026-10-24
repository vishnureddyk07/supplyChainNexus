from datetime import UTC, datetime, timedelta

import pytest
from psycopg.rows import dict_row

from services.demo.scenario import build_demo_scenario
from services.demo.seed import main as seed_demo
from services.risk.schemas import ShipmentFeatures
from services.risk.shipments import ShipmentFeatureRepository, ShipmentTrainingRepository


def test_demo_scenario_is_deterministic_and_explicitly_synthetic() -> None:
    anchor = datetime(2026, 10, 24, 12, tzinfo=UTC)

    first = build_demo_scenario(anchor)
    second = build_demo_scenario(anchor)

    assert len(first.events) == 140
    assert len(first.shipments) == 60
    assert len(first.risk_labels) == 40
    assert len(first.dependencies) == 10
    assert [event.event_id for event in first.events] == [
        event.event_id for event in second.events
    ]
    assert all(
        event.traceability is not None and event.traceability.simulated
        for event in first.events
    )
    assert {label[2] for label in first.risk_labels} == {"low", "high"}
    assert all(shipment.origin_name.startswith("Demo ") for shipment in first.shipments)


def test_demo_seed_refuses_to_run_outside_explicit_demo_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(RuntimeError, match="development-demo"):
        seed_demo()


def test_shipment_feature_queries_apply_strict_forecast_time_cutoff() -> None:
    forecast_at = datetime(2026, 10, 24, 12, tzinfo=UTC)

    class Cursor:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.queries = []
            self.responses = iter(
                [
                    {
                        "shipment_id": "shipment-1",
                        "supplier_external_id": "supplier-1",
                        "origin_name": "Origin",
                        "destination_name": "Destination",
                        "planned_departure": forecast_at,
                        "planned_arrival": forecast_at + timedelta(hours=12),
                    },
                    {"mean_delay": 1.5},
                    {"count": 2, "delay_rate": 0.5},
                    {"count": 1},
                    {"total": 4, "alerted": 2},
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            del _args
            return False

        def execute(self, query, params):
            self.queries.append((query, params))
            return Cursor(next(self.responses))

    connection = Connection()

    def connection_factory(_dsn, *, connect_timeout, row_factory):
        assert _dsn == "postgresql://example"
        assert connect_timeout == 5
        assert row_factory is dict_row
        return connection

    features = ShipmentFeatureRepository(
        "postgresql://example",
        connection_factory=connection_factory,
    ).snapshot("shipment-1", include_as_of=False)

    assert features.planned_transit_hours == 12
    assert features.supplier_delay_rate_90d == 0.5
    for query, params in connection.queries[1:]:
        assert "actual_arrival < %s" in query or "detected_at < %s" in query or "occurred_at < %s" in query
        assert params[-1] == forecast_at


def test_shipment_training_repository_excludes_simulated_labels_by_default() -> None:
    forecast_at = datetime(2026, 10, 24, 12, tzinfo=UTC)
    actual_arrival = forecast_at + timedelta(hours=1)
    captured_queries = []

    class Cursor:
        def fetchall(self):
            return [
                {
                    "shipment_id": "shipment-1",
                    "actual_arrival": actual_arrival,
                    "planned_arrival": forecast_at,
                    "planned_departure": forecast_at - timedelta(hours=8),
                }
            ]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            del _args
            return False

        def execute(self, query, params):
            captured_queries.append((query, params))
            return Cursor()

    def connection_factory(_dsn, *, connect_timeout, row_factory):
        assert _dsn == "postgresql://example"
        assert connect_timeout == 5
        assert row_factory is dict_row
        return Connection()

    class FeatureRepository:
        def snapshot(self, shipment_id, *, as_of, include_as_of):
            assert shipment_id == "shipment-1"
            assert include_as_of is False
            return ShipmentFeatures(
                shipment_id=shipment_id,
                as_of=as_of,
                planned_transit_hours=8,
            )

    examples = ShipmentTrainingRepository(
        "postgresql://example",
        feature_repository=FeatureRepository(),
        connection_factory=connection_factory,
    ).load_examples()

    assert len(examples) == 1
    assert examples[0].actual_delay_hours == 1
    assert "(NOT simulated OR %s)" in captured_queries[0][0]
    assert captured_queries[0][1] == (False,)
