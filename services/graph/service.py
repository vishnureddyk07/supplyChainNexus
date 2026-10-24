from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from supplychain_nexus.contracts import SupplyChainEvent
from services.graph.schemas import DependencyPath, GraphReadiness, SupplierGraphView

logger = logging.getLogger(__name__)

_CONSTRAINTS = (
    "CREATE CONSTRAINT supplier_external_id_unique IF NOT EXISTS "
    "FOR (n:Supplier) REQUIRE n.external_id IS UNIQUE",
    "CREATE CONSTRAINT supply_chain_event_id_unique IF NOT EXISTS "
    "FOR (n:SupplyChainEvent) REQUIRE n.event_id IS UNIQUE",
    "CREATE CONSTRAINT facility_external_id_unique IF NOT EXISTS "
    "FOR (n:Facility) REQUIRE n.external_id IS UNIQUE",
    "CREATE CONSTRAINT shipment_external_id_unique IF NOT EXISTS "
    "FOR (n:Shipment) REQUIRE n.external_id IS UNIQUE",
)

_UPSERT_EVENT = """
MERGE (supplier:Supplier {external_id: $supplier_id})
ON CREATE SET supplier.created_at = datetime($timestamp)
MERGE (event:SupplyChainEvent {event_id: $event_id})
ON CREATE SET
    event.schema_version = $schema_version,
    event.event_type = $event_type,
    event.source_system = $source_system,
    event.occurred_at = datetime($timestamp),
    event.payload_json = $payload_json
MERGE (supplier)-[:HAS_EVENT]->(event)
RETURN supplier.external_id AS supplier_id
"""

_UPDATE_SUPPLIER = """
MATCH (supplier:Supplier {external_id: $supplier_id})
WITH supplier
WHERE supplier.last_supplier_event_at IS NULL
   OR datetime($timestamp) >= supplier.last_supplier_event_at
SET supplier.name = $name,
    supplier.contact_email = $contact_email,
    supplier.phone = $phone,
    supplier.country = $country,
    supplier.status = $status,
    supplier.last_supplier_event_at = datetime($timestamp)
"""

_UPDATE_TELEMETRY = """
MATCH (supplier:Supplier {external_id: $supplier_id})
WITH supplier
WHERE supplier.last_telemetry_at IS NULL
   OR datetime($timestamp) >= supplier.last_telemetry_at
SET supplier.last_telemetry_at = datetime($timestamp),
    supplier.last_temperature = $temperature,
    supplier.last_humidity = $humidity
"""

_UPSERT_FACILITY = """
MERGE (facility:Facility {external_id: $facility_id})
ON CREATE SET facility.created_at = datetime($timestamp)
MERGE (supplier:Supplier {external_id: $supplier_id})
MERGE (supplier)-[:ASSOCIATED_WITH]->(facility)
"""

_UPSERT_SHIPMENT = """
MERGE (shipment:Shipment {external_id: $shipment_id})
ON CREATE SET shipment.created_at = datetime($timestamp)
MERGE (supplier:Supplier {external_id: $supplier_id})
MERGE (supplier)-[:ASSOCIATED_WITH]->(shipment)
"""


class SupplyChainGraph:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    @classmethod
    def from_env(cls, *, ensure_schema: bool = True) -> SupplyChainGraph:
        uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        username = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        timeout = int(os.getenv("DEPENDENCY_STARTUP_TIMEOUT_SECONDS", "120"))
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            driver: Driver | None = None
            try:
                driver = GraphDatabase.driver(
                    uri,
                    auth=(username, password),
                    connection_timeout=5,
                    max_connection_lifetime=3600,
                )
                driver.verify_connectivity()
                graph = cls(driver)
                if ensure_schema:
                    graph.ensure_schema()
                logger.info("connected to Neo4j", extra={"uri": uri})
                return graph
            except (ServiceUnavailable, Neo4jError, OSError) as exc:
                last_error = exc
                if driver is not None:
                    driver.close()
                logger.warning(
                    "Neo4j is not ready; retrying",
                    extra={"uri": uri, "error": str(exc)},
                )
                time.sleep(2)

        raise RuntimeError(f"Neo4j did not become ready within {timeout} seconds") from last_error

    def ensure_schema(self) -> None:
        with self._driver.session() as session:
            for statement in _CONSTRAINTS:
                session.run(statement).consume()

    def upsert_event(self, event: SupplyChainEvent) -> None:
        """Idempotently project the event; callers retry before committing Kafka offsets."""
        timestamp = event.timestamp.isoformat()
        payload = event.model_dump(mode="json")
        with self._driver.session() as session:
            session.execute_write(
                self._write_event,
                event,
                timestamp,
                payload,
            )
        logger.info(
            "event projected to Neo4j",
            extra={
                "event_id": str(event.event_id),
                "supplier_id": event.supplier_id,
            },
        )

    @staticmethod
    def _write_event(
        transaction: Any,
        event: SupplyChainEvent,
        timestamp: str,
        payload: dict[str, Any],
    ) -> None:
        transaction.run(
            _UPSERT_EVENT,
            supplier_id=event.supplier_id,
            event_id=str(event.event_id),
            schema_version=event.schema_version,
            event_type=event.event_type,
            source_system=event.source_system,
            timestamp=timestamp,
            payload_json=json.dumps(payload, sort_keys=True),
        ).consume()

        if event.supplier_data is not None:
            transaction.run(
                _UPDATE_SUPPLIER,
                supplier_id=event.supplier_id,
                timestamp=timestamp,
                name=event.supplier_data.name,
                contact_email=event.supplier_data.contact_email,
                phone=event.supplier_data.phone,
                country=event.supplier_data.country,
                status=event.supplier_data.status,
            ).consume()
        if event.sensor_measurements is not None:
            transaction.run(
                _UPDATE_TELEMETRY,
                supplier_id=event.supplier_id,
                timestamp=timestamp,
                temperature=event.sensor_measurements.temperature,
                humidity=event.sensor_measurements.humidity,
            ).consume()
        if event.facility_id:
            transaction.run(
                _UPSERT_FACILITY,
                supplier_id=event.supplier_id,
                facility_id=event.facility_id,
                timestamp=timestamp,
            ).consume()
        if event.shipment_id:
            transaction.run(
                _UPSERT_SHIPMENT,
                supplier_id=event.supplier_id,
                shipment_id=event.shipment_id,
                timestamp=timestamp,
            ).consume()

    def get_supplier(self, supplier_id: str) -> SupplierGraphView | None:
        query = """
        MATCH (supplier:Supplier {external_id: $supplier_id})
        OPTIONAL MATCH (supplier)-[:HAS_EVENT]->(event:SupplyChainEvent)
        OPTIONAL MATCH (supplier)-[:ASSOCIATED_WITH]->(facility:Facility)
        OPTIONAL MATCH (supplier)-[:ASSOCIATED_WITH]->(shipment:Shipment)
        RETURN properties(supplier) AS supplier,
               collect(DISTINCT properties(event)) AS events,
               collect(DISTINCT properties(facility)) AS facilities,
               collect(DISTINCT properties(shipment)) AS shipments
        """
        with self._driver.session() as session:
            record = session.run(query, supplier_id=supplier_id).single()
        if record is None or record["supplier"] is None:
            return None
        events = [item for item in record["events"] if item]
        facilities = [item for item in record["facilities"] if item]
        shipments = [item for item in record["shipments"] if item]
        return SupplierGraphView(
            supplier_id=supplier_id,
            supplier=_graph_value(record["supplier"]),
            events=_graph_value(events),
            facilities=_graph_value(facilities),
            shipments=_graph_value(shipments),
            retrieved_at=datetime.now(UTC),
        )

    def graph_payload(
        self,
        limit: int = 250,
        supplier_id: str | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if supplier_id:
            query = """
            MATCH (supplier:Supplier {external_id: $supplier_id})
            OPTIONAL MATCH (supplier)-[:HAS_EVENT|ASSOCIATED_WITH]-(connected)
            WITH collect(DISTINCT supplier) + collect(DISTINCT connected) AS candidates
            UNWIND candidates AS node
            WITH DISTINCT node WHERE node IS NOT NULL
            WITH node ORDER BY
                CASE WHEN 'Supplier' IN labels(node) THEN 0 ELSE 1 END,
                coalesce(node.occurred_at, node.created_at, datetime()) DESC
            LIMIT $limit
            WITH collect(node) AS nodes
            UNWIND nodes AS source
            OPTIONAL MATCH (source)-[relationship]-(target)
            WHERE target IN nodes
            RETURN nodes,
                   collect(DISTINCT {
                       source: elementId(startNode(relationship)),
                       target: elementId(endNode(relationship)),
                       type: type(relationship)
                   }) AS relationships
            """
        else:
            query = """
            MATCH (node)
            WHERE node:Supplier OR node:SupplyChainEvent OR node:Facility OR node:Shipment
            WITH node ORDER BY
                CASE WHEN node:Supplier THEN 0 ELSE 1 END,
                coalesce(node.occurred_at, node.created_at, datetime()) DESC
            LIMIT $limit
            WITH collect(node) AS nodes
            UNWIND nodes AS source
            OPTIONAL MATCH (source)-[relationship]-(target)
            WHERE target IN nodes
            RETURN nodes,
                   collect(DISTINCT {
                       source: elementId(startNode(relationship)),
                       target: elementId(endNode(relationship)),
                       type: type(relationship)
                   }) AS relationships
            """
        with self._driver.session() as session:
            record = session.run(
                query,
                supplier_id=supplier_id,
                limit=limit,
            ).single()
        if record is None:
            return {
                "nodes": [],
                "edges": [],
                "dependency_relationships_available": False,
            }
        nodes = []
        for node in record["nodes"]:
            properties = {
                key: _graph_value(value) for key, value in dict(node).items()
            }
            identifier = (
                properties.get("external_id")
                or properties.get("event_id")
                or str(node.element_id)
            )
            nodes.append(
                {
                    "id": str(node.element_id),
                    "label": next(iter(node.labels), "Entity"),
                    "identifier": str(identifier),
                    "properties": properties,
                }
            )
        edges = [
            {
                "source": relationship["source"],
                "target": relationship["target"],
                "type": relationship["type"],
            }
            for relationship in record["relationships"]
            if relationship["source"] and relationship["target"]
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "dependency_relationships_available": any(
                edge["type"] == "SUPPLIES" for edge in edges
            ),
        }

    def get_dependency_paths(
        self,
        supplier_id: str,
        max_hops: int = 3,
    ) -> list[DependencyPath]:
        if not 1 <= max_hops <= 5:
            raise ValueError("max_hops must be between 1 and 5")
        query = f"""
        MATCH (source:Supplier {{external_id: $supplier_id}})
        MATCH path=(source)-[*1..{max_hops}]->(target:Supplier)
        WHERE all(relationship IN relationships(path)
                  WHERE type(relationship) = 'SUPPLIES')
        RETURN [node IN nodes(path) | node.external_id] AS supplier_ids,
               length(path) AS hop_count
        ORDER BY hop_count
        LIMIT 100
        """
        with self._driver.session() as session:
            records = session.run(query, supplier_id=supplier_id)
            return [
                DependencyPath(
                    supplier_ids=record["supplier_ids"],
                    hop_count=record["hop_count"],
                )
                for record in records
            ]

    def upsert_supply_dependency(
        self,
        supplier_id: str,
        upstream_supplier_id: str,
        *,
        simulated: bool = False,
    ) -> None:
        if not supplier_id or not upstream_supplier_id or supplier_id == upstream_supplier_id:
            raise ValueError("supply relationship requires two different supplier IDs")
        query = """
        MATCH (supplier:Supplier {external_id: $supplier_id})
        MATCH (upstream:Supplier {external_id: $upstream_supplier_id})
        MERGE (supplier)-[relationship:SUPPLIES]->(upstream)
        SET relationship.simulated = $simulated
        """
        with self._driver.session() as session:
            session.run(
                query,
                supplier_id=supplier_id,
                upstream_supplier_id=upstream_supplier_id,
                simulated=simulated,
            ).consume()

    def get_supplier_dependency_count(self, supplier_id: str) -> int | None:
        query = """
        OPTIONAL MATCH ()-[known_relationship]->()
        WITH count(
            CASE WHEN type(known_relationship) = 'SUPPLIES'
                 THEN known_relationship END
        ) AS known_relationship_count
        MATCH (supplier:Supplier {external_id: $supplier_id})
        OPTIONAL MATCH (supplier)-[relationship]-(dependency:Supplier)
        RETURN known_relationship_count,
               count(DISTINCT CASE
                   WHEN type(relationship) = 'SUPPLIES' THEN dependency
               END) AS connected_supplier_count
        """
        with self._driver.session() as session:
            record = session.run(query, supplier_id=supplier_id).single()
        if record is None or record["known_relationship_count"] == 0:
            return None
        return record["connected_supplier_count"]

    def readiness(self) -> GraphReadiness:
        query = """
        OPTIONAL MATCH (supplier:Supplier)
        WITH count(supplier) AS suppliers
        OPTIONAL MATCH (event:SupplyChainEvent)
        WITH suppliers, count(event) AS events
        OPTIONAL MATCH ()-[has_event]->()
        WITH suppliers, events,
             count(CASE WHEN type(has_event) = 'HAS_EVENT' THEN has_event END)
                 AS has_event_relationships
        OPTIONAL MATCH ()-[relationship]->()
        RETURN suppliers, events, has_event_relationships,
               count(CASE
                   WHEN type(relationship) = 'SUPPLIES' THEN relationship
               END) AS supplier_dependencies
        """
        with self._driver.session() as session:
            record = session.run(query).single()
        if record is None:
            return GraphReadiness(ready=True, node_counts={}, relationship_counts={})
        return GraphReadiness(
            ready=True,
            node_counts={
                "Supplier": record["suppliers"],
                "SupplyChainEvent": record["events"],
            },
            relationship_counts={
                "HAS_EVENT": record["has_event_relationships"],
                "SUPPLIES": record["supplier_dependencies"],
            },
            note="No shipment, facility, or supplier-dependency facts are currently ingested.",
        )

    def close(self) -> None:
        self._driver.close()


def _graph_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {key: _graph_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_graph_value(item) for item in value]
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
