from datetime import UTC, datetime

import pytest

from supplychain_nexus.contracts import SupplyChainEvent


@pytest.fixture
def sensor_event() -> SupplyChainEvent:
    return SupplyChainEvent(
        event_type="sensor.telemetry",
        timestamp=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
        supplier_id="supplier-001",
        source_system="sensor_simulator",
        sensor_measurements={"temperature": 23.5, "humidity": 45},
        traceability={"simulated": True},
    )
