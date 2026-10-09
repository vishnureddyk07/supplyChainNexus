from services.graph.models import Company, map_event
from services.risk_engine.queries import DEPENDENCY_TRAVERSAL, MAX_HOPS


def test_supplier_mapping_materializes_companies_and_supplies():
    mapped = map_event({
        "source": "supplier_erp",
        "event_type": "supplier_mapping",
        "event_id": "event-1",
        "payload": {
            "supplier_id": "supplier-1",
            "supplier_name": "Acme",
            "consumer_id": "manufacturer-1",
        },
    })

    assert {node.company_id for node in mapped.nodes if isinstance(node, Company)} == {
        "supplier-1",
        "manufacturer-1",
    }
    assert mapped.relationships[0].relationship_type == "SUPPLIES"


def test_alternative_and_shipment_route_relationships_are_mapped():
    mapped = map_event({
        "source": "shipping",
        "event_type": "shipment_update",
        "event_id": "event-2",
        "payload": {
            "supplier_id": "supplier-1",
            "alternative_supplier_id": "supplier-2",
            "shipment_id": "shipment-1",
            "route_id": "route-1",
        },
    })

    assert {relationship.relationship_type for relationship in mapped.relationships} == {
        "ALTERNATIVE_FOR",
        "SHIPS_VIA",
    }


def test_dependency_query_is_hard_capped():
    assert MAX_HOPS == 5
    assert "[:SUPPLIES*1..5]" in DEPENDENCY_TRAVERSAL
