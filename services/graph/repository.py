from __future__ import annotations

from typing import Any

from .models import Company, RelationshipMapping, Route, Shipment

NODE_QUERIES = {
    Company: """
        MERGE (n:Company {company_id: $id})
        SET n.name = $name, n.country = $country, n.status = $status,
            n.source = $source, n.last_event_id = $last_event_id,
            n.updated_at = datetime()
    """,
    Shipment: """
        MERGE (n:Shipment {shipment_id: $id})
        SET n.origin = $origin, n.destination = $destination, n.status = $status,
            n.supplier_id = $supplier_id, n.consumer_id = $consumer_id,
            n.route_id = $route_id, n.source = $source,
            n.last_event_id = $last_event_id, n.updated_at = datetime()
    """,
    Route: """
        MERGE (n:Route {route_id: $id})
        SET n.origin = $origin, n.destination = $destination, n.mode = $mode,
            n.source = $source, n.last_event_id = $last_event_id,
            n.updated_at = datetime()
    """,
}

RELATIONSHIP_QUERY = """
MATCH (a:{start_label} {{{start_key}: $start_id}})
MATCH (b:{end_label} {{{end_key}: $end_id}})
MERGE (a)-[r:{relationship_type}]->(b)
SET r.updated_at = datetime()
"""


def _node_params(node: Company | Shipment | Route) -> dict[str, Any]:
    values = dict(node.properties)
    values["id"] = node.company_id if isinstance(node, Company) else node.shipment_id if isinstance(node, Shipment) else node.route_id
    values.update({key: value for key, value in vars(node).items() if key != "properties"})
    values.pop("company_id", None)
    values.pop("shipment_id", None)
    values.pop("route_id", None)
    values["source"] = node.properties.get("source")
    values["last_event_id"] = node.properties.get("last_event_id")
    return values


class GraphRepository:
    """Neo4j adapter; all writes are MERGE-based and safe to replay."""

    def __init__(self, driver: Any) -> None:
        self.driver = driver

    async def ensure_schema(self) -> None:
        """Create identity constraints once; MERGE then uses indexed keys."""
        statements = (
            "CREATE CONSTRAINT company_identity IF NOT EXISTS FOR (n:Company) REQUIRE n.company_id IS UNIQUE",
            "CREATE CONSTRAINT shipment_identity IF NOT EXISTS FOR (n:Shipment) REQUIRE n.shipment_id IS UNIQUE",
            "CREATE CONSTRAINT route_identity IF NOT EXISTS FOR (n:Route) REQUIRE n.route_id IS UNIQUE",
        )
        async with self.driver.session() as session:
            for statement in statements:
                await session.run(statement)

    async def upsert(self, mapped: Any) -> None:
        async with self.driver.session() as session:
            async with session.begin_transaction() as tx:
                for node in mapped.nodes:
                    await tx.run(NODE_QUERIES[type(node)], **_node_params(node))
                for relationship in mapped.relationships:
                    await tx.run(
                        RELATIONSHIP_QUERY.format(
                            start_label=relationship.start_label,
                            start_key={"Company": "company_id", "Shipment": "shipment_id", "Route": "route_id"}[relationship.start_label],
                            end_label=relationship.end_label,
                            end_key={"Company": "company_id", "Shipment": "shipment_id", "Route": "route_id"}[relationship.end_label],
                            relationship_type=relationship.relationship_type,
                        ),
                        start_id=relationship.start_id,
                        end_id=relationship.end_id,
                    )

    async def close(self) -> None:
        await self.driver.close()
