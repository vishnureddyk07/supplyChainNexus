import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from services.risk_engine.app import app, repository  # noqa: E402


def setup_function() -> None:
    repository.suppliers.clear()
    repository.risks.clear()
    repository.disruptions.clear()


def test_risk_score_is_explainable_and_duplicate_safe() -> None:
    with TestClient(app) as client:
        payload = {
            "supplier_id": "s-1", "event_id": "evt-1",
            "delivery_delay_days": 12, "defect_rate": 0.10,
            "financial_health": 0.5, "telemetry": {"temperature_zscore": 3.2},
        }
        first = client.post("/risk/score", json=payload)
        second = client.post("/risk/score", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["score"] == second.json()["score"]
    assert first.json()["reasons"]
    assert second.json()["duplicate"] is True
    assert "temperature" in first.json()["abnormal_telemetry"]


def test_supplier_and_disruption_api_validation() -> None:
    with TestClient(app) as client:
        assert client.post("/suppliers", json={"supplier_id": "s-2", "name": "Acme"}).status_code == 200
        assert client.get("/suppliers/s-2").json()["name"] == "Acme"
        created = client.post("/disruptions", json={
            "supplier_id": "s-2", "event_id": "d-1", "disruption_type": "port",
            "severity": "high", "message": "Port closed",
        })
        assert created.status_code == 200
        assert len(client.get("/disruptions?supplier_id=s-2").json()) == 1
        assert client.post("/risk/score", json={"supplier_id": "s-2", "defect_rate": 2}).status_code == 422
