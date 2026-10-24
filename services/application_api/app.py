from __future__ import annotations

import json
import logging
import os
import hmac
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j.exceptions import Neo4jError
from psycopg.rows import dict_row

from services.application_api.schemas import (
    GraphPayload,
    IncidentCreate,
    IncidentUpdate,
    Page,
    RecommendationRequest,
    RecommendationResponse,
)
from services.graph.service import SupplyChainGraph
from services.risk.composite import CompositeRiskScorer
from services.risk.explainability import explain_supplier_prediction
from services.risk.features import SupplierFeatureRepository
from services.risk.explainability import explain_shipment_prediction
from services.risk.schemas import ModelReadiness
from services.risk.shipments import ShipmentFeatureRepository
from services.risk.shipment_model import ShipmentDelayModel
from services.risk.supplier_model import SupplierRiskModel
from supplychain_nexus.contracts import SupplyChainEvent
from supplychain_nexus.logging_config import configure_logging

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/supplychain",
)
security = HTTPBearer(auto_error=False)
_ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}
_INCIDENT_TRANSITIONS = {
    "open": {"investigating", "resolved"},
    "investigating": {"mitigating", "resolved"},
    "mitigating": {"investigating", "resolved"},
    "resolved": set(),
}
_graph_instance: SupplyChainGraph | None = None
_graph_lock = Lock()


def _database() -> Any:
    return psycopg.connect(DATABASE_URL, connect_timeout=5, row_factory=dict_row)


def _authorized(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    _require_role("viewer", credentials)


def _operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    _require_role("operator", credentials)


def _require_role(
    required_role: str,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    role_tokens = {
        role: os.getenv(f"API_{role.upper()}_TOKEN")
        for role in _ROLE_RANK
    }
    if not any(role_tokens.values()):
        legacy_token = os.getenv("API_AUTH_TOKEN")
        if not legacy_token:
            return
        role_tokens["admin"] = legacy_token
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    role = next(
        (
            configured_role
            for configured_role, configured_token in role_tokens.items()
            if configured_token
            and hmac.compare_digest(credentials.credentials, configured_token)
        ),
        None,
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if _ROLE_RANK[role] < _ROLE_RANK[required_role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def _has_role_auth_configured() -> bool:
    if os.getenv("API_AUTH_TOKEN"):
        return True
    return any(os.getenv(f"API_{role.upper()}_TOKEN") for role in _ROLE_RANK)


def _demo_mode() -> bool:
    return os.getenv("APP_MODE", "operational").lower() == "development-demo"


def _model_evaluation(model_path: str) -> dict[str, Any] | None:
    evaluation_path = Path(model_path).with_suffix(
        Path(model_path).suffix + ".evaluation.json"
    )
    if not evaluation_path.is_file():
        return None
    try:
        result = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("model evaluation metadata could not be read")
        raise HTTPException(
            status_code=503,
            detail="Model evaluation metadata is invalid",
        ) from exc
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=503,
            detail="Model evaluation metadata is invalid",
        )
    return result


def _shipment_detail_payload(shipment: dict[str, Any]) -> dict[str, Any]:
    return {
        "shipment": _json_value(shipment),
        "mode": "development-demo" if _demo_mode() else "operational",
        "synthetic": shipment["simulated"],
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _graph_instance
    _validate_deployment_configuration()
    try:
        yield
    finally:
        if _graph_instance is not None:
            _graph_instance.close()
            _graph_instance = None


def _validate_deployment_configuration() -> None:
    if os.getenv("APP_ENV", "development").lower() != "production":
        return
    tokens = [
        os.getenv("API_VIEWER_TOKEN", ""),
        os.getenv("API_OPERATOR_TOKEN", ""),
        os.getenv("API_ADMIN_TOKEN", ""),
    ]
    if (
        any(len(token) < 32 for token in tokens)
        or len(set(tokens)) != len(tokens)
    ):
        raise RuntimeError(
            "production requires distinct API role tokens with at least 32 characters: "
            "API_VIEWER_TOKEN, "
            "API_OPERATOR_TOKEN, and API_ADMIN_TOKEN values"
        )
    configured_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if not configured_origins:
        raise RuntimeError("production requires explicit CORS_ORIGINS")
    for origin in configured_origins:
        try:
            parsed_origin = urlsplit(origin)
            parsed_origin.port
        except ValueError as exc:
            raise RuntimeError(
                "production CORS_ORIGINS must contain only explicit HTTPS origins"
            ) from exc
        if (
            parsed_origin.scheme != "https"
            or not parsed_origin.hostname
            or "*" in parsed_origin.hostname
            or parsed_origin.username
            or parsed_origin.password
            or parsed_origin.path not in ("", "/")
            or parsed_origin.query
            or parsed_origin.fragment
        ):
            raise RuntimeError(
                "production CORS_ORIGINS must contain only explicit HTTPS origins"
            )


app = FastAPI(
    title="SupplyChainNexus Control Tower API",
    version="1.0.0",
    lifespan=lifespan,
)
origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(psycopg.Error)
async def database_error_handler(_: Request, exc: psycopg.Error) -> JSONResponse:
    logger.exception("application database operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Database service unavailable"})


@app.exception_handler(Neo4jError)
async def graph_error_handler(_: Request, exc: Neo4jError) -> JSONResponse:
    logger.exception("application graph operation failed", exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": "Graph service unavailable"})


def _graph() -> SupplyChainGraph:
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance
    try:
        with _graph_lock:
            if _graph_instance is None:
                _graph_instance = SupplyChainGraph.from_env(ensure_schema=False)
        return _graph_instance
    except (RuntimeError, OSError) as exc:
        logger.exception("Neo4j connection failed")
        raise HTTPException(status_code=503, detail="Graph service unavailable") from exc


def _supplier_model() -> SupplierRiskModel | None:
    path = Path(os.getenv("SUPPLIER_RISK_MODEL_PATH", "model-artifacts/supplier-risk-rf.skops"))
    if not path.is_file():
        return None
    try:
        return SupplierRiskModel.load(path)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.exception("supplier model could not be loaded")
        raise HTTPException(status_code=503, detail="Supplier model artifact is invalid") from exc


def _shipment_model() -> ShipmentDelayModel | None:
    path = Path(os.getenv("SHIPMENT_DELAY_MODEL_PATH", "model-artifacts/shipment-delay.txt"))
    if not path.is_file():
        return None
    try:
        return ShipmentDelayModel.load(path)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.exception("shipment model could not be loaded")
        raise HTTPException(status_code=503, detail="Shipment model artifact is invalid") from exc


def _page_query(
    *,
    page: int,
    page_size: int,
) -> tuple[int, int]:
    return (page - 1) * page_size, page_size


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health", dependencies=[Depends(_authorized)])
def service_health() -> dict[str, Any]:
    services: dict[str, Any] = {
        "api": {"ready": True},
        "authentication": {
            "enabled": _has_role_auth_configured(),
            "local_mode_only": not _has_role_auth_configured(),
        },
    }
    try:
        with _database() as connection:
            connection.execute("SELECT 1")
        services["postgres"] = {"ready": True}
    except psycopg.Error:
        logger.exception("PostgreSQL health probe failed")
        services["postgres"] = {"ready": False}
    try:
        graph = _graph()
        services["neo4j"] = graph.readiness().model_dump(mode="json")
    except (HTTPException, Neo4jError):
        services["neo4j"] = {"ready": False}
    return {"services": services}


@app.get("/api/v1/models/readiness", dependencies=[Depends(_authorized)])
def model_readiness() -> dict[str, ModelReadiness]:
    with _database() as connection:
        source_names = tuple(
            value.strip()
            for value in os.getenv(
                "SUPPLIER_RISK_LABEL_SOURCES", "manual,audited"
            ).split(",")
            if value.strip()
        )
        risk_examples = connection.execute(
            """
            SELECT count(*) AS count
            FROM supplier_risk_scores AS score
            WHERE score.score_source = ANY(%s)
            """,
            (list(source_names),),
        ).fetchone()["count"]
        shipment_count = connection.execute(
            """
            SELECT count(*) AS count FROM shipments
            WHERE actual_arrival IS NOT NULL
              AND (NOT simulated OR %s)
            """,
            (_demo_mode(),),
        ).fetchone()["count"]
    supplier_model = _supplier_model()
    shipment_model = _shipment_model()
    risk_ready = supplier_model is not None
    shipment_ready = shipment_model is not None
    return {
        "supplier_risk": ModelReadiness(
            model_name="supplier-risk-random-forest",
            ready=risk_ready,
            sample_count=(
                supplier_model.training_sample_count
                if supplier_model
                else risk_examples
            ),
            label_source=", ".join(source_names) or None,
            reason=None if risk_ready else "A trained model artifact is not available.",
            development_model=(
                supplier_model.development_model if supplier_model else False
            ),
            evaluation=_model_evaluation(
                os.getenv(
                    "SUPPLIER_RISK_MODEL_PATH",
                    "model-artifacts/supplier-risk-rf.skops",
                )
            ),
        ),
        "shipment_delay": ModelReadiness(
            model_name="shipment-delay-lightgbm",
            ready=shipment_ready,
            sample_count=(
                shipment_model.training_sample_count
                if shipment_model
                else shipment_count
            ),
            label_source="verified actual shipment delay labels",
            reason=(
                None
                if shipment_ready
                else "No shipment outcomes or trained model artifact are available."
            ),
            development_model=(
                shipment_model.development_model if shipment_model else False
            ),
            evaluation=_model_evaluation(
                os.getenv(
                    "SHIPMENT_DELAY_MODEL_PATH",
                    "model-artifacts/shipment-delay.txt",
                )
            ),
        ),
    }


@app.get("/api/v1/dashboard", dependencies=[Depends(_authorized)])
def dashboard() -> dict[str, Any]:
    with _database() as connection:
        supplier_count = connection.execute(
            "SELECT count(*) AS count FROM suppliers"
        ).fetchone()["count"]
        event_counts = connection.execute(
            """
            SELECT count(*) AS count,
                   count(*) FILTER (
                       WHERE payload->'traceability'->>'simulated' = 'true'
                   ) AS simulated
            FROM supply_chain_events
            """
        ).fetchone()
        shipment_counts = connection.execute(
            """
            SELECT count(*) FILTER (WHERE %s OR NOT simulated) AS total,
                   count(*) FILTER (WHERE simulated) AS simulated
            FROM shipments
            """,
            (_demo_mode(),),
        ).fetchone()
        event_count = event_counts["count"]
        disruption = connection.execute(
            """
            SELECT count(*) AS count
            FROM disruption_log
            WHERE resolved_at IS NULL
            """
        ).fetchone()["count"]
        risk_distribution = connection.execute(
            """
            SELECT latest.risk_category, count(*) AS count
            FROM (
                SELECT DISTINCT ON (supplier_id)
                       supplier_id, risk_category, scored_at
                FROM supplier_risk_scores
                WHERE scored_at <= NOW()
                ORDER BY supplier_id, scored_at DESC, id DESC
            ) AS latest
            GROUP BY latest.risk_category
            ORDER BY latest.risk_category
            """
        ).fetchall()
        sensor_alerts = connection.execute(
            """
            SELECT count(*) AS count
            FROM supply_chain_events
            WHERE source_system = 'sensor_simulator'
              AND event_type = 'sensor.telemetry'
              AND received_at >= NOW() - INTERVAL '24 hours'
              AND (
                  (payload->'sensor_measurements'->>'temperature')::double precision > %s
                  OR (payload->'sensor_measurements'->>'humidity')::double precision > %s
              )
            """,
            (
                float(os.getenv("TEMPERATURE_ALERT_C", "45")),
                float(os.getenv("HUMIDITY_ALERT_PERCENT", "80")),
            ),
        ).fetchone()["count"]
        daily = connection.execute(
            """
            SELECT date_trunc('day', received_at) AS day, count(*) AS count
            FROM supply_chain_events
            WHERE received_at >= NOW() - INTERVAL '14 days'
            GROUP BY 1 ORDER BY 1
            """
        ).fetchall()
        recent_events = connection.execute(
            """
            SELECT event_id, event_type, source_system, supplier_external_id,
                   occurred_at, received_at, payload
            FROM supply_chain_events ORDER BY received_at DESC LIMIT 10
            """
        ).fetchall()
        recent_incidents = connection.execute(
            "SELECT * FROM incidents ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
    graph_ready = False
    try:
        graph = _graph()
        graph_ready = graph.readiness().ready
    except (HTTPException, Neo4jError):
        pass
    return {
        "kpis": {
            "suppliers": supplier_count,
            "events": event_count,
            "sensor_alerts_24h": sensor_alerts,
            "open_disruptions": disruption,
            "shipments": shipment_counts["total"],
        },
        "data_provenance": {
            "simulated_events": event_counts["simulated"],
            "simulated_shipments": shipment_counts["simulated"],
            "synthetic_data_present": (
                event_counts["simulated"] > 0
                or shipment_counts["simulated"] > 0
                or _demo_mode()
            ),
            "mode": "development-demo" if _demo_mode() else "operational",
        },
        "risk_distribution": [
            {"category": item["risk_category"], "count": item["count"]}
            for item in risk_distribution
        ],
        "event_activity": [
            {"date": item["day"].date().isoformat(), "count": item["count"]}
            for item in daily
        ],
        "recent_events": [_event_dict(item) for item in recent_events],
        "recent_incidents": [_incident_dict(item) for item in recent_incidents],
        "model_readiness": model_readiness(),
        "service_readiness": {
            "postgres": True,
            "neo4j": graph_ready,
        },
    }


@app.get("/api/v1/suppliers", response_model=Page, dependencies=[Depends(_authorized)])
def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    status_filter: str | None = Query(None, alias="status", max_length=40),
) -> Page:
    where = []
    params: list[Any] = []
    if search:
        where.append("(s.name ILIKE %s OR s.external_id ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if status_filter:
        where.append("s.metadata->>'status' = %s")
        params.append(status_filter)
    clause = " WHERE " + " AND ".join(where) if where else ""
    offset, limit = _page_query(page=page, page_size=page_size)
    with _database() as connection:
        total = connection.execute(
            "SELECT count(*) AS count FROM suppliers AS s" + clause, params
        ).fetchone()["count"]
        rows = connection.execute(
            """
            SELECT s.id, s.external_id, s.name, s.domain, s.metadata,
                   s.created_at, s.updated_at,
                   (SELECT max(e.occurred_at) FROM supply_chain_events e
                    WHERE e.supplier_external_id = s.external_id) AS last_event_at,
                   (SELECT score.risk_category FROM supplier_risk_scores score
                    WHERE score.supplier_id = s.id AND score.scored_at <= NOW()
                    ORDER BY score.scored_at DESC, score.id DESC LIMIT 1)
                       AS assessed_risk_category,
                   (SELECT score.risk_score FROM supplier_risk_scores score
                    WHERE score.supplier_id = s.id AND score.scored_at <= NOW()
                    ORDER BY score.scored_at DESC, score.id DESC LIMIT 1)
                       AS assessed_risk_score
            FROM suppliers AS s
            """
            + clause
            + " ORDER BY s.updated_at DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return Page(items=[_json_value(item) for item in rows], page=page, page_size=page_size, total=total)


@app.get("/api/v1/suppliers/{supplier_id}", dependencies=[Depends(_authorized)])
def supplier_detail(supplier_id: str) -> dict[str, Any]:
    with _database() as connection:
        supplier = connection.execute(
            "SELECT * FROM suppliers WHERE external_id = %s", (supplier_id,)
        ).fetchone()
    if supplier is None:
        with _database() as connection:
            observed = connection.execute(
                """
                SELECT supplier_external_id, max(occurred_at) AS last_event_at
                FROM supply_chain_events
                WHERE supplier_external_id = %s
                GROUP BY supplier_external_id
                """,
                (supplier_id,),
            ).fetchone()
        if observed is None:
            raise HTTPException(status_code=404, detail="Supplier not found")
        supplier = {
            "id": None,
            "external_id": supplier_id,
            "name": supplier_id,
            "domain": None,
            "metadata": None,
            "created_at": None,
            "updated_at": None,
            "last_event_at": observed["last_event_at"],
            "identity_source": "event_only",
        }
    features = SupplierFeatureRepository(DATABASE_URL).snapshot(supplier_id)
    assessment = CompositeRiskScorer.from_env().assess(features)
    model = _supplier_model()
    prediction = model.predict(features) if model else None
    if model:
        assessment = CompositeRiskScorer.from_env().assess(
            features, supplier_prediction=prediction
        )
    graph_supplier = None
    try:
        graph = _graph()
        view = graph.get_supplier(supplier_id)
        graph_supplier = view.model_dump(mode="json") if view else None
    except (HTTPException, Neo4jError):
        graph_supplier = None
    return {
        "supplier": _json_value(supplier),
        "features": features.model_dump(mode="json"),
        "assessment": assessment.model_dump(mode="json"),
        "prediction": prediction.model_dump(mode="json") if prediction else None,
        "explanation": (
            explain_supplier_prediction(model, features).model_dump(mode="json")
            if model
            else None
        ),
        "graph": graph_supplier,
    }


@app.get("/api/v1/suppliers/{supplier_id}/events", response_model=Page, dependencies=[Depends(_authorized)])
def supplier_events(
    supplier_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Page:
    return _events_page(supplier_id=supplier_id, page=page, page_size=page_size)


@app.get("/api/v1/events", response_model=Page, dependencies=[Depends(_authorized)])
def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    supplier_id: str | None = Query(None, max_length=200),
    event_type: str | None = Query(None, max_length=100),
    source_system: str | None = Query(None, max_length=100),
    since: datetime | None = None,
    until: datetime | None = None,
) -> Page:
    if since and since.utcoffset() is None:
        raise HTTPException(status_code=422, detail="since must include a timezone offset")
    if until and until.utcoffset() is None:
        raise HTTPException(status_code=422, detail="until must include a timezone offset")
    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must not be later than until")
    filters = []
    params: list[Any] = []
    for field, value in (
        ("supplier_external_id", supplier_id),
        ("event_type", event_type),
        ("source_system", source_system),
    ):
        if value:
            filters.append(f"{field} = %s")
            params.append(value)
    if since:
        filters.append("occurred_at >= %s")
        params.append(since)
    if until:
        filters.append("occurred_at <= %s")
        params.append(until)
    return _query_events(filters, params, page, page_size)


def _events_page(supplier_id: str, page: int, page_size: int) -> Page:
    return _query_events(
        ["supplier_external_id = %s"],
        [supplier_id],
        page,
        page_size,
    )


def _query_events(
    filters: list[str],
    params: list[Any],
    page: int,
    page_size: int,
) -> Page:
    clause = " WHERE " + " AND ".join(filters) if filters else ""
    offset, limit = _page_query(page=page, page_size=page_size)
    with _database() as connection:
        total = connection.execute(
            "SELECT count(*) AS count FROM supply_chain_events" + clause, params
        ).fetchone()["count"]
        rows = connection.execute(
            """
            SELECT e.event_id, e.schema_version, e.event_type, e.source_system,
                   e.supplier_external_id, e.occurred_at, e.received_at, e.payload,
                   EXISTS (
                     SELECT 1 FROM graph_projection_state g WHERE g.event_id = e.event_id
                   ) AS graph_projected
            FROM supply_chain_events e
            """
            + clause
            + " ORDER BY occurred_at DESC, event_id DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return Page(
        items=[_event_dict(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@app.get("/api/v1/shipments", response_model=Page, dependencies=[Depends(_authorized)])
def list_shipments(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    supplier_id: str | None = Query(None, max_length=200),
    simulated: bool | None = None,
) -> Page:
    clauses = []
    params: list[Any] = []
    if supplier_id:
        clauses.append("supplier_external_id = %s")
        params.append(supplier_id)
    if simulated is not None:
        clauses.append("simulated = %s")
        params.append(simulated)
    if not _demo_mode():
        clauses.append("simulated = FALSE")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    offset, limit = _page_query(page=page, page_size=page_size)
    with _database() as connection:
        total = connection.execute(
            "SELECT count(*) AS count FROM shipments" + where,
            params,
        ).fetchone()["count"]
        rows = connection.execute(
            """
            SELECT shipment_id, supplier_external_id, origin_name,
                   origin_latitude, origin_longitude, destination_name,
                   destination_latitude, destination_longitude,
                   planned_departure, planned_arrival, actual_arrival,
                   CASE WHEN actual_arrival IS NULL THEN NULL ELSE
                     GREATEST(EXTRACT(EPOCH FROM (actual_arrival - planned_arrival))
                              / 3600.0, 0)
                   END AS actual_delay_hours,
                   simulated, created_at, updated_at
            FROM shipments
            """
            + where
            + " ORDER BY planned_departure DESC, shipment_id LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return Page(
        items=[_json_value(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@app.get("/api/v1/shipments/{shipment_id}", dependencies=[Depends(_authorized)])
def shipment_detail(shipment_id: str) -> dict[str, Any]:
    with _database() as connection:
        shipment = connection.execute(
            """
            SELECT shipment_id, supplier_external_id, origin_name,
                   origin_latitude, origin_longitude, destination_name,
                   destination_latitude, destination_longitude,
                   planned_departure, planned_arrival, actual_arrival,
                   CASE WHEN actual_arrival IS NULL THEN NULL ELSE
                     GREATEST(EXTRACT(EPOCH FROM (actual_arrival - planned_arrival))
                              / 3600.0, 0)
                   END AS actual_delay_hours,
                   simulated, created_at, updated_at
            FROM shipments WHERE shipment_id = %s
            """,
            (shipment_id,),
        ).fetchone()
    if shipment is None or (shipment["simulated"] and not _demo_mode()):
        raise HTTPException(status_code=404, detail="Shipment not found")
    return _shipment_detail_payload(shipment)


@app.get("/api/v1/shipments/{shipment_id}/prediction", dependencies=[Depends(_authorized)])
def shipment_prediction(shipment_id: str) -> dict[str, Any]:
    with _database() as connection:
        shipment = connection.execute(
            """
            SELECT shipment_id, supplier_external_id, planned_departure,
                   simulated
            FROM shipments WHERE shipment_id = %s
            """,
            (shipment_id,),
        ).fetchone()
    if shipment is None or (shipment["simulated"] and not _demo_mode()):
        raise HTTPException(status_code=404, detail="Shipment not found")
    model = _shipment_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Shipment prediction unavailable: a trained model artifact is not available.",
        )
    features = ShipmentFeatureRepository(DATABASE_URL).snapshot(
        shipment_id,
        as_of=shipment["planned_departure"],
        include_as_of=False,
    )
    prediction = model.predict(features)
    evaluation = _model_evaluation(
        os.getenv("SHIPMENT_DELAY_MODEL_PATH", "model-artifacts/shipment-delay.txt")
    )
    return {
        "prediction": prediction.model_dump(mode="json"),
        "features": features.model_dump(mode="json"),
        "explanation": explain_shipment_prediction(model, features).model_dump(mode="json"),
        "evaluation": evaluation,
        "simulated": shipment["simulated"],
        "prediction_is_retrospective": shipment["planned_departure"] < datetime.now(
            shipment["planned_departure"].tzinfo
        ),
    }


@app.get("/api/v1/graph", response_model=GraphPayload, dependencies=[Depends(_authorized)])
def graph_data(
    limit: int = Query(250, ge=1, le=1000),
    supplier_id: str | None = Query(None, max_length=200),
) -> GraphPayload:
    graph = _graph()
    return graph.graph_payload(limit=limit, supplier_id=supplier_id)


@app.get("/api/v1/graph/suppliers/{supplier_id}/dependencies", dependencies=[Depends(_authorized)])
def supplier_dependencies(
    supplier_id: str,
    max_hops: int = Query(3, ge=1, le=5),
) -> dict[str, Any]:
    graph = _graph()
    paths = graph.get_dependency_paths(supplier_id, max_hops=max_hops)
    return {
        "supplier_id": supplier_id,
        "available": graph.get_supplier_dependency_count(supplier_id) is not None,
        "paths": [path.model_dump(mode="json") for path in paths],
    }


@app.get("/api/v1/incidents", response_model=Page, dependencies=[Depends(_authorized)])
def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    incident_status: str | None = Query(None, alias="status"),
) -> Page:
    where = " WHERE status = %s" if incident_status else ""
    params = [incident_status] if incident_status else []
    offset, limit = _page_query(page=page, page_size=page_size)
    with _database() as connection:
        total = connection.execute(
            "SELECT count(*) AS count FROM incidents" + where, params
        ).fetchone()["count"]
        rows = connection.execute(
            "SELECT * FROM incidents"
            + where
            + " ORDER BY updated_at DESC LIMIT %s OFFSET %s",
            [*params, limit, offset],
        ).fetchall()
    return Page(
        items=[_incident_dict(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


@app.post("/api/v1/incidents", status_code=201, dependencies=[Depends(_operator)])
def create_incident(payload: IncidentCreate) -> dict[str, Any]:
    with _database() as connection:
        event_supplier_id = None
        if payload.event_id:
            event = connection.execute(
                """
                SELECT supplier_external_id
                FROM supply_chain_events
                WHERE event_id = %s
                """,
                (payload.event_id,),
            ).fetchone()
            if not event:
                raise HTTPException(status_code=422, detail="Referenced event does not exist")
            event_supplier_id = event["supplier_external_id"]
            if (
                payload.supplier_external_id
                and payload.supplier_external_id != event_supplier_id
            ):
                raise HTTPException(
                    status_code=422,
                    detail="Referenced event belongs to a different supplier",
                )
        if payload.supplier_external_id:
            exists = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM suppliers WHERE external_id = %s
                    UNION ALL
                    SELECT 1 FROM supply_chain_events
                    WHERE supplier_external_id = %s
                ) AS exists
                """,
                (payload.supplier_external_id, payload.supplier_external_id),
            ).fetchone()
            if not exists["exists"] and payload.supplier_external_id != event_supplier_id:
                raise HTTPException(status_code=422, detail="Referenced supplier does not exist")
        incident = connection.execute(
            """
            INSERT INTO incidents (
                title, description, severity, status, owner,
                supplier_external_id, event_id, investigation_notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                payload.title.strip(),
                payload.description.strip(),
                payload.severity.value,
                payload.status.value,
                payload.owner,
                payload.supplier_external_id,
                payload.event_id,
                payload.investigation_notes,
            ),
        ).fetchone()
    logger.info("incident created", extra={"incident_id": str(incident["id"])})
    return _incident_dict(incident)


@app.patch("/api/v1/incidents/{incident_id}", dependencies=[Depends(_operator)])
def update_incident(incident_id: UUID, payload: IncidentUpdate) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one update field is required")
    for field in ("title", "description", "severity", "status", "investigation_notes"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} must not be null")
    assignments = []
    values = []
    for field, value in changes.items():
        if field in {"status", "severity"} and value is not None:
            value = value.value
        elif isinstance(value, str) and field in {"title", "description"}:
            value = value.strip()
        assignments.append(f"{field} = %s")
        values.append(value)
    assignments.append("updated_at = NOW()")
    with _database() as connection:
        current = connection.execute(
            "SELECT status FROM incidents WHERE id = %s FOR UPDATE",
            (incident_id,),
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        requested_status = changes.get("status")
        if requested_status is not None:
            requested_value = requested_status.value
            if (
                requested_value != current["status"]
                and requested_value not in _INCIDENT_TRANSITIONS.get(
                    current["status"], set()
                )
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Incident status cannot transition from {current['status']} "
                        f"to {requested_value}"
                    ),
                )
        row = connection.execute(
            f"UPDATE incidents SET {', '.join(assignments)} WHERE id = %s RETURNING *",
            [*values, incident_id],
        ).fetchone()
    logger.info("incident updated", extra={"incident_id": str(incident_id)})
    return _incident_dict(row)


@app.post(
    "/api/v1/recommendations",
    response_model=RecommendationResponse,
    dependencies=[Depends(_authorized)],
)
def recommendations(request: RecommendationRequest) -> RecommendationResponse:
    evidence: list[str] = []
    uncertainty: list[str] = []
    context: dict[str, Any] = {}
    with _database() as connection:
        if request.supplier_id:
            row = connection.execute(
                """
                SELECT s.external_id, s.name, s.metadata,
                       count(e.event_id) AS event_count,
                       max(e.occurred_at) AS last_event_at
                FROM suppliers s
                LEFT JOIN supply_chain_events e
                  ON e.supplier_external_id = s.external_id
                WHERE s.external_id = %s
                GROUP BY s.id
                """,
                (request.supplier_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Supplier not found")
            features = SupplierFeatureRepository(DATABASE_URL).snapshot(request.supplier_id)
            assessment = CompositeRiskScorer.from_env().assess(features)
            model = _supplier_model()
            prediction = model.predict(features) if model else None
            context["supplier"] = {
                "supplier_id": row["external_id"],
                "name": row["name"],
                "event_count": row["event_count"],
                "last_event_at": _iso(row["last_event_at"]),
                "assessment": assessment.model_dump(mode="json"),
                "prediction": prediction.model_dump(mode="json") if prediction else None,
            }
            evidence.append(f"Persisted event count: {row['event_count']}.")
            if prediction:
                evidence.append(
                    f"Trained model {prediction.model_version} predicted category "
                    f"{prediction.category.value}."
                )
            else:
                uncertainty.append("No trained supplier-risk model artifact is available.")
            if assessment.score is not None:
                evidence.append(
                    f"Composite heuristic score {assessment.score:.1f}/100 "
                    f"(coverage {assessment.coverage:.0%})."
                )
            else:
                uncertainty.append("Composite risk severity is unknown due to limited coverage.")
        if request.event_id:
            row = connection.execute(
                """
                SELECT event_id, event_type, source_system, supplier_external_id,
                       occurred_at, payload
                FROM supply_chain_events WHERE event_id = %s
                """,
                (request.event_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Event not found")
            evidence.append(
                f"Persisted event {row['event_id']} is {row['event_type']} "
                f"from {row['source_system']}."
            )
            event_model = SupplyChainEvent.model_validate(row["payload"])
            context["event"] = {
                "event_id": str(row["event_id"]),
                "event_type": row["event_type"],
                "source_system": row["source_system"],
                "supplier_id": row["supplier_external_id"],
                "occurred_at": row["occurred_at"].isoformat(),
                "sensor_measurements": (
                    event_model.sensor_measurements.model_dump(mode="json")
                    if event_model.sensor_measurements
                    else None
                ),
                "supplier_status": (
                    event_model.supplier_data.status
                    if event_model.supplier_data
                    else None
                ),
            }
            if event_model.sensor_measurements:
                measurements = event_model.sensor_measurements
                evidence.append(
                    f"Recorded sensor measurements: temperature "
                    f"{measurements.temperature} °C and humidity "
                    f"{measurements.humidity}%."
                )
            if event_model.supplier_data:
                evidence.append(
                    f"Supplier status in event: {event_model.supplier_data.status}."
                )
        if not request.supplier_id and not request.event_id:
            raise HTTPException(
                status_code=422,
                detail="Provide a supplier_id or event_id to ground the recommendation",
            )
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    if not (deployment and endpoint and api_key):
        return RecommendationResponse(
            available=False,
            generated=False,
            evidence=evidence,
            uncertainty=uncertainty,
            reason="Azure OpenAI is not configured; no recommendation was generated.",
        )
    body = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Provide cautious supply-chain investigation suggestions based only on "
                    "the supplied JSON evidence. Distinguish facts from inferences. Never "
                    "claim an action was executed. Mention missing or uncertain evidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"question": request.question, "evidence": context},
                    default=str,
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={api_version}"
    )
    try:
        response = httpx.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        response.raise_for_status()
        result = response.json()["choices"][0]["message"]["content"]
        return RecommendationResponse(
            available=True,
            generated=True,
            model=deployment,
            recommendation=result,
            evidence=evidence,
            uncertainty=uncertainty,
        )
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        logger.exception("Azure OpenAI recommendation request failed")
        return RecommendationResponse(
            available=False,
            generated=False,
            evidence=evidence,
            uncertainty=uncertainty,
            reason=f"Azure OpenAI request failed ({type(exc).__name__}); no recommendation was generated.",
        )


def _event_dict(row: dict[str, Any]) -> dict[str, Any]:
    result = _json_value(row)
    if "payload" in result and isinstance(result["payload"], dict):
        event = SupplyChainEvent.model_validate(result["payload"])
        result["traceability"] = event.traceability.model_dump(mode="json") if event.traceability else None
    return result


def _incident_dict(row: dict[str, Any]) -> dict[str, Any]:
    return _json_value(row)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "as_tuple"):
        return float(value)
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
