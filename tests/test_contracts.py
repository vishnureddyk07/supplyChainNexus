from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.supplier_erp_mock_imports import generate_supplier
from supplychain_nexus.contracts import (
    SupplyChainEvent,
    event_from_json_bytes,
    event_to_json_bytes,
    normalize_event_payload,
)


def test_event_round_trip_preserves_contract(sensor_event: SupplyChainEvent) -> None:
    restored = event_from_json_bytes(event_to_json_bytes(sensor_event))
    assert restored == sensor_event
    assert restored.schema_version == 1
    assert restored.traceability.simulated is True


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {
                "event_type": "sensor.telemetry",
                "timestamp": "2026-10-24T08:00:00Z",
                "supplier_id": "supplier-001",
                "source_system": "sensor_simulator",
                "sensor_measurements": {"temperature": 22},
            },
            "humidity",
        ),
        (
            {
                "event_type": "sensor.telemetry",
                "timestamp": "2026-10-24T08:00:00",
                "supplier_id": "supplier-001",
                "source_system": "sensor_simulator",
                "sensor_measurements": {"temperature": 22, "humidity": 45},
            },
            "UTC offset",
        ),
        (
            {
                "event_type": "sensor.telemetry",
                "timestamp": "2026-10-24T08:00:00Z",
                "supplier_id": "supplier-001",
                "source_system": "sensor_simulator",
                "sensor_measurements": {"temperature": 22, "humidity": 101},
            },
            "less than or equal to 100",
        ),
        (
            {
                "event_type": "sensor.telemetry",
                "timestamp": 1792828800,
                "supplier_id": "supplier-001",
                "source_system": "sensor_simulator",
                "sensor_measurements": {"temperature": 22, "humidity": 45},
            },
            "ISO 8601",
        ),
    ],
)
def test_invalid_events_are_rejected(payload: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        SupplyChainEvent.model_validate(payload)


def test_unexpected_fields_are_rejected(sensor_event: SupplyChainEvent) -> None:
    payload = sensor_event.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SupplyChainEvent.model_validate(payload)


def test_legacy_sensor_payload_gets_stable_id() -> None:
    payload = {
        "supplierId": "supplier-001",
        "temperature": 25.2,
        "humidity": 50,
        "timestamp": "2026-10-24T08:00:00+00:00",
    }
    first = normalize_event_payload(payload)
    duplicate = normalize_event_payload(payload)
    assert first.event_id == duplicate.event_id
    assert first.source_system == "sensor_simulator"
    assert first.traceability.simulated


def test_erp_generator_emits_shared_contract() -> None:
    event = generate_supplier()
    assert event.source_system == "supplier_erp"
    assert event.event_type.startswith("supplier.")
    assert event.supplier_data is not None
    assert event.traceability.simulated
    assert isinstance(event.event_id, UUID)
    assert isinstance(event.timestamp, datetime)


def test_legacy_erp_event_is_normalized() -> None:
    payload = {
        "supplier_id": "supplier-erp-1",
        "supplier_name": "Example Supplier",
        "contact_email": "ops@example.test",
        "phone": "555-0100",
        "country": "Exampleland",
        "status": "ACTIVE",
        "event_type": "SUPPLIER_UPDATED",
        "timestamp": "2026-10-24T08:00:00+00:00",
    }
    event = normalize_event_payload(payload)
    duplicate = normalize_event_payload(payload)
    assert event.event_type == "supplier.updated"
    assert event.event_id == duplicate.event_id
    assert event.supplier_data is not None
    assert event.supplier_data.name == "Example Supplier"


def test_legacy_event_rejects_unexpected_fields() -> None:
    with pytest.raises(ValueError, match="unexpected fields"):
        normalize_event_payload(
            {
                "supplierId": "supplier-001",
                "temperature": 20,
                "humidity": 45,
                "timestamp": "2026-10-24T08:00:00Z",
                "unrecognized": True,
            }
        )
