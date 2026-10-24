from __future__ import annotations

from importlib import import_module
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from services.application_api.app import app
from services.application_api.schemas import IncidentUpdate


def _clear_auth(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    for name in (
        "API_AUTH_TOKEN",
        "API_VIEWER_TOKEN",
        "API_OPERATOR_TOKEN",
        "API_ADMIN_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_health_endpoint_is_available_without_application_auth(monkeypatch) -> None:
    _clear_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_role_authentication_requires_token_for_protected_routes(monkeypatch) -> None:
    monkeypatch.setenv("API_VIEWER_TOKEN", "viewer-test-token")
    monkeypatch.setenv("API_OPERATOR_TOKEN", "operator-test-token")
    monkeypatch.setenv("API_ADMIN_TOKEN", "admin-test-token")

    with TestClient(app) as client:
        assert client.get("/api/v1/events").status_code == 401
        assert (
            client.get(
                "/api/v1/events?page_size=101",
                headers={"Authorization": "Bearer viewer-test-token"},
            ).status_code
            == 422
        )
        viewer_write = client.post(
            "/api/v1/incidents",
            headers={"Authorization": "Bearer viewer-test-token"},
            json={
                "title": "Test",
                "description": "Test investigation",
                "severity": "low",
            },
        )

    assert viewer_write.status_code == 403


def test_list_endpoint_validates_page_bounds_before_database_access(monkeypatch) -> None:
    _clear_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.get("/api/v1/suppliers?page=0&page_size=101")

    assert response.status_code == 422


def test_incident_schema_rejects_invalid_status_and_unexpected_fields(monkeypatch) -> None:
    _clear_auth(monkeypatch)
    with TestClient(app) as client:
        invalid_status = client.post(
            "/api/v1/incidents",
            json={
                "title": "Investigation",
                "description": "A recorded review",
                "severity": "low",
                "status": "invented",
            },
        )
        unexpected = client.post(
            "/api/v1/incidents",
            json={
                "title": "Investigation",
                "description": "A recorded review",
                "severity": "low",
                "executed_action": True,
            },
        )

    assert invalid_status.status_code == 422
    assert unexpected.status_code == 422


def test_incident_update_can_clear_owner_but_rejects_blank_required_text() -> None:
    assert IncidentUpdate(owner=None).model_dump(exclude_unset=True) == {"owner": None}
    assert IncidentUpdate(investigation_notes="  ").model_dump(exclude_unset=True) == {
        "investigation_notes": ""
    }
    with pytest.raises(ValueError, match="must not be blank"):
        IncidentUpdate(title="   ")


def test_graph_driver_is_reused_until_application_shutdown(monkeypatch) -> None:
    class GraphStub:
        close_calls = 0

        def graph_payload(self, **_kwargs):
            return {
                "nodes": [],
                "edges": [],
                "dependency_relationships_available": False,
            }

        def close(self):
            self.close_calls += 1

    graph = GraphStub()
    api_module = import_module("services.application_api.app")
    monkeypatch.setattr(api_module, "_graph_instance", graph)

    with TestClient(app) as client:
        assert client.get("/api/v1/graph").status_code == 200
        assert client.get("/api/v1/graph").status_code == 200
        assert graph.close_calls == 0

    assert graph.close_calls == 1


@pytest.mark.parametrize(
    ("tokens", "origins"),
    [
        (("v" * 32, "o" * 32, "a" * 32), ""),
        (("s" * 32, "s" * 32, "a" * 32), "https://control.example.test"),
        (("v" * 32, "o" * 32, "a" * 32), "http://control.example.test"),
        (("short", "o" * 32, "a" * 32), "https://control.example.test"),
    ],
)
def test_production_startup_fails_closed_for_invalid_security_configuration(
    monkeypatch, tokens, origins
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_VIEWER_TOKEN", tokens[0])
    monkeypatch.setenv("API_OPERATOR_TOKEN", tokens[1])
    monkeypatch.setenv("API_ADMIN_TOKEN", tokens[2])
    monkeypatch.setenv("CORS_ORIGINS", origins)

    with pytest.raises(RuntimeError, match="production"):
        with TestClient(app):
            pass


def test_production_api_accepts_distinct_long_tokens_and_explicit_https_origin(
    monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_VIEWER_TOKEN", "v" * 32)
    monkeypatch.setenv("API_OPERATOR_TOKEN", "o" * 32)
    monkeypatch.setenv("API_ADMIN_TOKEN", "a" * 32)
    monkeypatch.setenv("CORS_ORIGINS", "https://control.example.test")

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_incident_status_transition_rejects_skipping_mitigation(monkeypatch) -> None:
    api_module = import_module("services.application_api.app")

    class Cursor:
        def fetchone(self):
            return {"status": "open"}

    class Connection:
        calls = 0

        def execute(self, query, _params):
            self.calls += 1
            assert "FOR UPDATE" in query
            return Cursor()

    connection = Connection()

    class Database:
        def __enter__(self):
            return connection

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(api_module, "_database", lambda: Database())
    with pytest.raises(HTTPException) as error:
        api_module.update_incident(
            uuid4(),
            IncidentUpdate(status="mitigating"),
        )

    assert error.value.status_code == 409
    assert connection.calls == 1
