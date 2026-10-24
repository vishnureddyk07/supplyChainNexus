from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = 1
_LEGACY_EVENT_NAMESPACE = UUID("0e9550ee-873d-4cc7-bcfb-3b45bb57cc86")


def _legacy_event_id(payload: dict[str, object]) -> object:
    event_id = payload.get("event_id")
    if event_id is not None:
        return event_id
    canonical_payload = json.dumps(payload, sort_keys=True, default=str)
    return uuid5(_LEGACY_EVENT_NAMESPACE, canonical_payload)


def _reject_unexpected_legacy_fields(
    payload: dict[str, object],
    allowed_fields: set[str],
) -> None:
    unexpected = payload.keys() - allowed_fields
    if unexpected:
        fields = ", ".join(sorted(unexpected))
        raise ValueError(f"legacy event has unexpected fields: {fields}")


class SensorMeasurements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float = Field(allow_inf_nan=False)
    humidity: float = Field(ge=0, le=100, allow_inf_nan=False)


class SupplierData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    contact_email: str | None = None
    phone: str | None = None
    country: str | None = None
    status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("supplier name must not be blank")
        return value


class Traceability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID | None = None
    simulated: bool = False


class SupplyChainEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    schema_version: Literal[1] = SCHEMA_VERSION
    event_type: Literal[
        "sensor.telemetry",
        "supplier.created",
        "supplier.updated",
        "supplier.deleted",
    ]
    timestamp: datetime
    supplier_id: str = Field(min_length=1)
    source_system: Literal["sensor_simulator", "supplier_erp"]
    sensor_measurements: SensorMeasurements | None = None
    supplier_data: SupplierData | None = None
    shipment_id: str | None = None
    facility_id: str | None = None
    traceability: Traceability = Field(default_factory=Traceability)

    @field_validator("timestamp", mode="before")
    @classmethod
    def require_datetime_input(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("timestamp must be an ISO 8601 string or datetime")
        return value

    @field_validator("supplier_id")
    @classmethod
    def strip_supplier_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("supplier_id must not be blank")
        return value

    @model_validator(mode="after")
    def validate_event_payload(self) -> SupplyChainEvent:
        if self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a UTC offset")
        if self.event_type == "sensor.telemetry":
            if self.source_system != "sensor_simulator":
                raise ValueError("sensor.telemetry must come from sensor_simulator")
            if self.sensor_measurements is None or self.supplier_data is not None:
                raise ValueError(
                    "sensor.telemetry requires sensor_measurements and forbids supplier_data"
                )
        else:
            if self.source_system != "supplier_erp":
                raise ValueError("supplier lifecycle events must come from supplier_erp")
            if self.supplier_data is None or self.sensor_measurements is not None:
                raise ValueError(
                    "supplier lifecycle events require supplier_data and forbid sensor_measurements"
                )
        return self


def normalize_event_payload(
    payload: dict[str, object],
    *,
    source_system: str | None = None,
) -> SupplyChainEvent:
    """Validate current events and translate the project's original payload shapes."""
    if not isinstance(payload, dict):
        raise ValueError("event payload must be a JSON object")

    if "schema_version" in payload:
        return SupplyChainEvent.model_validate(payload)

    if "supplierId" in payload or "temperature" in payload:
        _reject_unexpected_legacy_fields(
            payload,
            {
                "event_id",
                "supplierId",
                "temperature",
                "humidity",
                "timestamp",
                "shipment_id",
                "facility_id",
                "traceability",
            },
        )
        supplier_id = payload.get("supplierId")
        if not isinstance(supplier_id, str):
            raise ValueError("legacy sensor event requires supplierId")
        normalized = {
            "event_id": _legacy_event_id(payload),
            "schema_version": SCHEMA_VERSION,
            "event_type": "sensor.telemetry",
            "timestamp": payload.get("timestamp"),
            "supplier_id": supplier_id,
            "source_system": source_system or "sensor_simulator",
            "sensor_measurements": {
                "temperature": payload.get("temperature"),
                "humidity": payload.get("humidity"),
            },
            "shipment_id": payload.get("shipment_id"),
            "facility_id": payload.get("facility_id"),
            "traceability": payload.get("traceability") or {"simulated": True},
        }
        return SupplyChainEvent.model_validate(normalized)

    if "supplier_name" in payload or "supplier_data" in payload:
        _reject_unexpected_legacy_fields(
            payload,
            {
                "event_id",
                "supplier_id",
                "supplier_name",
                "contact_email",
                "phone",
                "country",
                "status",
                "event_type",
                "timestamp",
                "supplier_data",
                "shipment_id",
                "facility_id",
                "traceability",
            },
        )
        supplier_id = payload.get("supplier_id")
        if not isinstance(supplier_id, str):
            raise ValueError("supplier event requires supplier_id")
        legacy_types = {
            "SUPPLIER_CREATED": "supplier.created",
            "SUPPLIER_UPDATED": "supplier.updated",
            "SUPPLIER_DELETED": "supplier.deleted",
        }
        event_type = payload.get("event_type")
        if isinstance(event_type, str) and event_type in legacy_types:
            event_type = legacy_types[event_type]
        normalized = {
            "event_id": _legacy_event_id(payload),
            "schema_version": SCHEMA_VERSION,
            "event_type": event_type,
            "timestamp": payload.get("timestamp"),
            "supplier_id": supplier_id,
            "source_system": source_system or "supplier_erp",
            "supplier_data": payload.get("supplier_data")
            or {
                "name": payload.get("supplier_name"),
                "contact_email": payload.get("contact_email"),
                "phone": payload.get("phone"),
                "country": payload.get("country"),
                "status": payload.get("status"),
            },
            "shipment_id": payload.get("shipment_id"),
            "facility_id": payload.get("facility_id"),
            "traceability": payload.get("traceability") or {"simulated": True},
        }
        return SupplyChainEvent.model_validate(normalized)

    raise ValueError("unrecognized event payload shape")


def event_to_json_bytes(event: SupplyChainEvent) -> bytes:
    return json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def event_from_json_bytes(payload: bytes) -> SupplyChainEvent:
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("event payload must be a JSON object")
    return normalize_event_payload(decoded)


__all__ = [
    "SCHEMA_VERSION",
    "SensorMeasurements",
    "SupplierData",
    "SupplyChainEvent",
    "Traceability",
    "ValidationError",
    "event_from_json_bytes",
    "event_to_json_bytes",
    "normalize_event_payload",
]
