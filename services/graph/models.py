from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _first(payload: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = payload.get(name)
        if value not in (None, ""):
            return value
    return None


@dataclass(frozen=True)
class Company:
    company_id: str
    name: str | None = None
    country: str | None = None
    status: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    origin: str | None = None
    destination: str | None = None
    status: str | None = None
    supplier_id: str | None = None
    consumer_id: str | None = None
    route_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Route:
    route_id: str
    origin: str | None = None
    destination: str | None = None
    mode: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationshipMapping:
    relationship_type: str
    start_label: str
    start_id: str
    end_label: str
    end_id: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MappedEvent:
    nodes: tuple[Company | Shipment | Route, ...] = ()
    relationships: tuple[RelationshipMapping, ...] = ()


def map_event(event: dict[str, Any]) -> MappedEvent:
    """Map the canonical ingestion envelope into graph entities.

    Source connectors evolve independently, so aliases are accepted while the
    graph identity fields remain strict. Events without a graph identity are
    rejected by the consumer and routed to its poison-message handler.
    """
    source = event.get("source")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("event payload must be an object")
    event_type = str(event.get("event_type", "")).lower()
    nodes: list[Company | Shipment | Route] = []
    relationships: list[RelationshipMapping] = []

    supplier_id = _first(payload, "supplier_id", "supplierId", "supplier")
    consumer_id = _first(payload, "consumer_id", "consumerId", "customer_id", "customerId")
    company_id = _first(payload, "company_id", "companyId")
    alternative_id = _first(payload, "alternative_supplier_id", "alternativeSupplierId", "alternative_id")

    def add_company(identifier: Any, name: Any = None) -> None:
        if not identifier or any(node.company_id == str(identifier) for node in nodes if isinstance(node, Company)):
            return
        nodes.append(Company(
            company_id=str(identifier),
            name=name or _first(payload, "company_name", "name"),
            country=_first(payload, "country", "country_code"),
            status=_first(payload, "status"),
            properties={"source": source, "last_event_id": event.get("event_id")},
        ))

    add_company(supplier_id or company_id, _first(payload, "supplier_name"))
    add_company(consumer_id, _first(payload, "consumer_name"))
    add_company(alternative_id, _first(payload, "alternative_supplier_name"))
    if source == "supplier_erp" and not nodes:
        raise ValueError("supplier_erp event requires supplier_id")

    shipment_id = _first(payload, "shipment_id", "shipmentId", "order_id", "orderId")
    if shipment_id:
        shipment = Shipment(
            shipment_id=str(shipment_id),
            origin=_first(payload, "origin", "origin_port"),
            destination=_first(payload, "destination", "destination_port"),
            status=_first(payload, "status"),
            supplier_id=str(supplier_id) if supplier_id else None,
            consumer_id=str(consumer_id) if consumer_id else None,
            route_id=str(_first(payload, "route_id", "routeId")) if _first(payload, "route_id", "routeId") else None,
            properties={"source": source, "last_event_id": event.get("event_id")},
        )
        nodes.append(shipment)
        if shipment.supplier_id and shipment.consumer_id:
            relationships.append(RelationshipMapping("SUPPLIES", "Company", shipment.supplier_id, "Company", shipment.consumer_id))

    if supplier_id and consumer_id and not any(
        relationship.relationship_type == "SUPPLIES"
        and relationship.start_id == str(supplier_id)
        and relationship.end_id == str(consumer_id)
        for relationship in relationships
    ):
        relationships.append(RelationshipMapping("SUPPLIES", "Company", str(supplier_id), "Company", str(consumer_id)))

    route_id = _first(payload, "route_id", "routeId", "voyage_id", "voyageId")
    if route_id:
        nodes.append(Route(
            route_id=str(route_id),
            origin=_first(payload, "origin", "origin_port"),
            destination=_first(payload, "destination", "destination_port"),
            mode=_first(payload, "mode", "transport_mode"),
            properties={"source": source, "last_event_id": event.get("event_id")},
        ))
        if shipment_id:
            relationships.append(RelationshipMapping("SHIPS_VIA", "Shipment", str(shipment_id), "Route", str(route_id)))

    if supplier_id and alternative_id:
        relationships.append(RelationshipMapping("ALTERNATIVE_FOR", "Company", str(alternative_id), "Company", str(supplier_id)))

    if not nodes and not relationships and event_type not in {"weather_observation", "geopolitical_news", "sensor_telemetry", "vessel_position"}:
        raise ValueError("event does not contain a graph identity")
    return MappedEvent(tuple(nodes), tuple(relationships))
