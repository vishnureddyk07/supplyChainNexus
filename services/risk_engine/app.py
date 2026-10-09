from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .engine import calculate_risk
from .models import Disruption, RiskRequest, RiskResponse, Supplier, TelemetryRequest
from .repository import Repository, now

app = FastAPI(title="Supply Chain Risk Engine", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
repository = Repository()


@app.on_event("startup")
async def startup() -> None:
    repository.initialize()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": repository.health(), "service": "risk-engine"}


@app.post("/suppliers", response_model=Supplier)
async def create_supplier(supplier: Supplier) -> Supplier:
    return Supplier(**repository.upsert_supplier(supplier.model_dump(exclude_none=True)))


@app.get("/suppliers", response_model=list[Supplier])
async def list_suppliers() -> list[Supplier]:
    return [Supplier(**value) for value in repository.suppliers.values()]


@app.get("/suppliers/{supplier_id}", response_model=Supplier)
async def get_supplier(supplier_id: str) -> Supplier:
    value = repository.get_supplier(supplier_id)
    if value is None:
        raise HTTPException(404, "supplier not found")
    return Supplier(**value)


@app.post("/risk/score", response_model=RiskResponse)
async def score_risk(request: RiskRequest) -> RiskResponse:
    if repository.get_supplier(request.supplier_id) is None:
        repository.upsert_supplier({"supplier_id": request.supplier_id, "status": "active"})
    score, level, reasons, abnormal = calculate_risk(request)
    calculated_at = request.observed_at or now()
    fingerprint_data = {"event_id": request.event_id} if request.event_id else {
        "supplier_id": request.supplier_id, "observed_at": request.observed_at.isoformat() if request.observed_at else None,
        "values": request.model_dump(mode="json", exclude={"observed_at"}),
    }
    record = {
        "supplier_id": request.supplier_id, "score": score, "level": level,
        "reasons": [r.model_dump() for r in reasons], "abnormal_telemetry": abnormal,
        "calculated_at": calculated_at, "fingerprint": repository._fingerprint(fingerprint_data),
    }
    saved, duplicate = repository.add_risk(record)
    return RiskResponse(**{key: value for key, value in saved.items() if key != "fingerprint"}, duplicate=duplicate)


@app.post("/risk/{supplier_id}", response_model=RiskResponse)
async def score_risk_legacy(supplier_id: str, request: RiskRequest) -> RiskResponse:
    if request.supplier_id != supplier_id:
        raise HTTPException(400, "supplier_id does not match path")
    return await score_risk(request)


@app.get("/risk/{supplier_id}", response_model=RiskResponse)
async def latest_risk(supplier_id: str) -> RiskResponse:
    history = repository.history(supplier_id)
    if not history:
        raise HTTPException(404, "risk history not found")
    return RiskResponse(**{key: value for key, value in history[0].items() if key != "fingerprint"})


@app.get("/risk/{supplier_id}/history", response_model=list[RiskResponse])
async def risk_history(supplier_id: str, limit: int = Query(50, ge=1, le=500)) -> list[RiskResponse]:
    return [RiskResponse(**{key: value for key, value in r.items() if key != "fingerprint"})
            for r in repository.history(supplier_id)[:limit]]


@app.post("/telemetry", response_model=RiskResponse)
async def telemetry(request: TelemetryRequest) -> RiskResponse:
    risk = RiskRequest(supplier_id=request.supplier_id, event_id=request.event_id,
                       telemetry=request.values, observed_at=request.observed_at)
    return await score_risk(risk)


@app.post("/disruptions", response_model=Disruption)
async def create_disruption(disruption: Disruption) -> Disruption:
    data = disruption.model_dump(exclude_none=True)
    data["created_at"] = now()
    data["fingerprint"] = repository._fingerprint(
        {"event_id": disruption.event_id} if disruption.event_id
        else {k: v for k, v in data.items() if k != "created_at"}
    )
    saved, _ = repository.add_disruption(data)
    return Disruption(**{k: v for k, v in saved.items() if k not in {"fingerprint", "created_at"}})


@app.get("/disruptions", response_model=list[Disruption])
async def disruptions(supplier_id: str | None = None) -> list[Disruption]:
    return [Disruption(**{k: v for k, v in d.items() if k not in {"fingerprint", "created_at"}})
            for d in repository.all_disruptions(supplier_id)]
