from __future__ import annotations

import json
import os
import urllib.request

import pytest

RUN_INTEGRATION = os.getenv("RUN_DEMO_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_INTEGRATION,
    reason="set RUN_DEMO_INTEGRATION=1 with the isolated demo Compose profile running",
)

DEMO_API_URL = os.getenv("DEMO_APPLICATION_API_URL", "http://localhost:8002")
OPERATIONAL_API_URL = os.getenv("APPLICATION_API_URL", "http://localhost:8001")


def _request(base_url: str, path: str) -> dict:
    headers = {}
    token = (
        os.getenv("API_OPERATOR_TOKEN")
        or os.getenv("API_VIEWER_TOKEN")
        or os.getenv("API_AUTH_TOKEN")
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{base_url}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def test_demo_api_serves_synthetic_shipments_models_and_graph_without_operational_leakage() -> None:
    dashboard = _request(DEMO_API_URL, "/api/v1/dashboard")
    shipments = _request(DEMO_API_URL, "/api/v1/shipments?page=1&page_size=1")
    readiness = _request(DEMO_API_URL, "/api/v1/models/readiness")
    graph = _request(DEMO_API_URL, "/api/v1/graph?limit=1000")
    operational_dashboard = _request(OPERATIONAL_API_URL, "/api/v1/dashboard")
    operational_shipments = _request(
        OPERATIONAL_API_URL, "/api/v1/shipments?page=1&page_size=1"
    )

    assert dashboard["data_provenance"]["mode"] == "development-demo"
    assert dashboard["data_provenance"]["synthetic_data_present"] is True
    assert dashboard["kpis"]["shipments"] > 0
    assert shipments["items"]
    shipment_id = shipments["items"][0]["shipment_id"]
    detail = _request(DEMO_API_URL, f"/api/v1/shipments/{shipment_id}")
    prediction = _request(
        DEMO_API_URL,
        f"/api/v1/shipments/{shipment_id}/prediction",
    )

    assert detail["synthetic"] is True
    assert prediction["simulated"] is True
    assert prediction["prediction"]["development_model"] is True
    assert prediction["evaluation"]["development_data"] is True
    assert prediction["evaluation"]["temporal_evaluation"]["evaluation_sample_count"] > 0
    assert prediction["explanation"]["contributions"]
    assert readiness["supplier_risk"]["development_model"] is True
    assert readiness["shipment_delay"]["development_model"] is True
    assert graph["dependency_relationships_available"] is True
    assert any(edge["type"] == "SUPPLIES" for edge in graph["edges"])
    assert operational_dashboard["data_provenance"]["mode"] != "development-demo"
    assert operational_dashboard["data_provenance"]["simulated_shipments"] == 0
    assert operational_shipments["total"] == 0
