from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5

from supplychain_nexus.contracts import SupplyChainEvent

SUPPLIER_COUNT = 40
SHIPMENT_COUNT = 60
DEMO_LABEL_SOURCE = "demo_synthetic"


@dataclass(frozen=True)
class DemoShipment:
    shipment_id: str
    supplier_id: str
    origin_name: str
    origin_latitude: float
    origin_longitude: float
    destination_name: str
    destination_latitude: float
    destination_longitude: float
    planned_departure: datetime
    planned_arrival: datetime
    actual_arrival: datetime


@dataclass(frozen=True)
class DemoScenario:
    anchor: datetime
    events: tuple[SupplyChainEvent, ...]
    shipments: tuple[DemoShipment, ...]
    risk_labels: tuple[tuple[str, float, str, datetime], ...]
    disruption_suppliers: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]


def build_demo_scenario(anchor: datetime) -> DemoScenario:
    if anchor.utcoffset() is None:
        raise ValueError("scenario anchor must include a UTC offset")
    anchor = anchor.astimezone(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    scenario_day = anchor.date().isoformat()
    suppliers = tuple(f"demo-supplier-{index:03}" for index in range(SUPPLIER_COUNT))
    events: list[SupplyChainEvent] = []
    labels: list[tuple[str, float, str, datetime]] = []

    for index, supplier_id in enumerate(suppliers):
        label_time = anchor - timedelta(days=SUPPLIER_COUNT - index)
        elevated = index % 2 == 0
        status = "SUSPENDED" if elevated else "ACTIVE"
        events.append(
            SupplyChainEvent(
                event_id=uuid5(NAMESPACE_URL, f"scn-demo:{scenario_day}:{supplier_id}:erp"),
                event_type="supplier.updated",
                timestamp=label_time - timedelta(hours=4),
                supplier_id=supplier_id,
                source_system="supplier_erp",
                supplier_data={
                    "name": f"Simulated Supplier {index + 1:02}",
                    "contact_email": f"operations-{index:03}@example.test",
                    "country": "DEMO",
                    "status": status,
                },
                traceability={"simulated": True},
            )
        )
        events.append(
            SupplyChainEvent(
                event_id=uuid5(NAMESPACE_URL, f"scn-demo:{scenario_day}:{supplier_id}:telemetry"),
                event_type="sensor.telemetry",
                timestamp=label_time - timedelta(hours=2),
                supplier_id=supplier_id,
                source_system="sensor_simulator",
                sensor_measurements={
                    "temperature": 54.0 if elevated else 22.0,
                    "humidity": 86.0 if elevated else 52.0,
                },
                facility_id=f"demo-facility-{index % 4 + 1:02}",
                traceability={"simulated": True},
            )
        )
        labels.append(
            (
                supplier_id,
                85.0 if elevated else 20.0,
                "high" if elevated else "low",
                label_time,
            )
        )

    route_points = (
        ("Demo Harbor", 37.7, -122.4),
        ("Demo Ridge", 39.7, -104.9),
        ("Demo Valley", 41.9, -87.6),
        ("Demo Summit", 33.4, -112.1),
    )
    shipments: list[DemoShipment] = []
    for index in range(SHIPMENT_COUNT):
        supplier_id = suppliers[index % SUPPLIER_COUNT]
        origin = route_points[index % len(route_points)]
        destination = route_points[(index + 1) % len(route_points)]
        departure = anchor - timedelta(days=90) + timedelta(days=index * 1.4)
        planned_arrival = departure + timedelta(hours=30 + index % 18)
        delay_hours = float((index * 7) % 13)
        shipment_id = f"demo-shipment-{index + 1:03}"
        shipments.append(
            DemoShipment(
                shipment_id=shipment_id,
                supplier_id=supplier_id,
                origin_name=origin[0],
                origin_latitude=origin[1],
                origin_longitude=origin[2],
                destination_name=destination[0],
                destination_latitude=destination[1],
                destination_longitude=destination[2],
                planned_departure=departure,
                planned_arrival=planned_arrival,
                actual_arrival=planned_arrival + timedelta(hours=delay_hours),
            )
        )
        events.append(
            SupplyChainEvent(
                event_id=uuid5(NAMESPACE_URL, f"scn-demo:{scenario_day}:{shipment_id}:telemetry"),
                event_type="sensor.telemetry",
                timestamp=departure - timedelta(hours=2),
                supplier_id=supplier_id,
                source_system="sensor_simulator",
                sensor_measurements={
                    "temperature": 51.0 if index % 3 == 0 else 22.0,
                    "humidity": 83.0 if index % 3 == 0 else 50.0,
                },
                shipment_id=shipment_id,
                facility_id=f"demo-facility-{index % 4 + 1:02}",
                traceability={"simulated": True},
            )
        )

    disruption_suppliers = tuple(suppliers[index] for index in range(0, SUPPLIER_COUNT, 8))
    dependencies = tuple(
        (suppliers[index], suppliers[index + 1])
        for index in range(0, SUPPLIER_COUNT - 1, 4)
    )
    return DemoScenario(
        anchor=anchor,
        events=tuple(events),
        shipments=tuple(shipments),
        risk_labels=tuple(labels),
        disruption_suppliers=disruption_suppliers,
        dependencies=dependencies,
    )


def scenario_for_today() -> DemoScenario:
    today = datetime.combine(date.today(), time(hour=12), tzinfo=UTC)
    return build_demo_scenario(today)
