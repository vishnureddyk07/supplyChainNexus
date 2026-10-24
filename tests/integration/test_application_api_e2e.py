from __future__ import annotations

import json
import os
import urllib.request
from uuid import uuid4

import psycopg
import pytest

RUN_INTEGRATION = os.getenv("RUN_APPLICATION_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="set RUN_APPLICATION_INTEGRATION=1 with the application Compose stack running",
)

API_URL = os.getenv("APPLICATION_API_URL", "http://localhost:8001")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/supplychain",
)


def _request(path: str, *, method: str = "GET", payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    token = os.getenv("API_TEST_TOKEN") or os.getenv("API_OPERATOR_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def test_dashboard_uses_persisted_database_and_reports_model_readiness() -> None:
    dashboard = _request("/api/v1/dashboard")
    readiness = _request("/api/v1/models/readiness")

    assert dashboard["kpis"]["suppliers"] >= 0
    assert dashboard["kpis"]["events"] >= 0
    assert (
        dashboard["data_provenance"]["simulated_events"]
        <= dashboard["kpis"]["events"]
    )
    assert isinstance(dashboard["data_provenance"]["synthetic_data_present"], bool)
    assert "event_activity" in dashboard
    assert "supplier_risk" in readiness
    assert "shipment_delay" in readiness


def test_graph_endpoint_returns_actual_projected_entities() -> None:
    graph = _request("/api/v1/graph?limit=100")

    assert isinstance(graph["nodes"], list)
    assert isinstance(graph["edges"], list)
    assert any(node["label"] == "SupplyChainEvent" for node in graph["nodes"])
    assert graph["dependency_relationships_available"] is False


def test_incident_status_and_notes_are_persisted() -> None:
    event_page = _request("/api/v1/events?page=1&page_size=1")
    assert event_page["items"], "the live pipeline should have a persisted event"
    event = event_page["items"][0]
    incident_id = None
    title = f"API integration test {uuid4()}"
    try:
        created = _request(
            "/api/v1/incidents",
            method="POST",
            payload={
                "title": title,
                "description": "Verify persisted application incident updates.",
                "severity": "low",
                "owner": "Integration test owner",
                "supplier_external_id": event["supplier_external_id"],
                "event_id": event["event_id"],
                "investigation_notes": "Created by an opt-in integration test.",
            },
        )
        incident_id = created["id"]
        assert created["status"] == "open"

        updated = _request(
            f"/api/v1/incidents/{incident_id}",
            method="PATCH",
            payload={
                "status": "investigating",
                "owner": "Operations test owner",
                "investigation_notes": "Status and notes persisted by API test.",
            },
        )
        assert updated["status"] == "investigating"
        assert updated["owner"] == "Operations test owner"
        assert updated["investigation_notes"] == "Status and notes persisted by API test."

        with psycopg.connect(DATABASE_URL) as connection:
            persisted = connection.execute(
                "SELECT status, owner, investigation_notes FROM incidents WHERE id = %s",
                (incident_id,),
            ).fetchone()
        assert persisted == (
            "investigating",
            "Operations test owner",
            "Status and notes persisted by API test.",
        )
    finally:
        if incident_id:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute("DELETE FROM incidents WHERE id = %s", (incident_id,))


def test_incident_can_reference_observed_event_only_supplier() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            """
            SELECT event.supplier_external_id
            FROM supply_chain_events AS event
            LEFT JOIN suppliers AS supplier
              ON supplier.external_id = event.supplier_external_id
            WHERE supplier.id IS NULL
            LIMIT 1
            """
        ).fetchone()
    assert row is not None, "the live data should include an event-only supplier"

    incident_id = None
    try:
        created = _request(
            "/api/v1/incidents",
            method="POST",
            payload={
                "title": f"Event-only supplier test {uuid4()}",
                "description": "Verify an observed supplier can be investigated.",
                "severity": "low",
                "supplier_external_id": row[0],
            },
        )
        incident_id = created["id"]
        assert created["supplier_external_id"] == row[0]
    finally:
        if incident_id:
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute("DELETE FROM incidents WHERE id = %s", (incident_id,))


def test_shipment_endpoint_reports_no_fabricated_records() -> None:
    shipments = _request("/api/v1/shipments?page=1&page_size=10")

    assert shipments == {"items": [], "page": 1, "page_size": 10, "total": 0}
