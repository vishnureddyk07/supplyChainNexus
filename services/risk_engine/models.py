"""Public request and response schemas for the risk service.

The schemas deliberately accept the names used by the ingestion connectors while
normalising them to a small, stable API contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Supplier(BaseModel):
    model_config = ConfigDict(extra="allow")
    supplier_id: str = Field(min_length=1, max_length=128)
    name: str | None = None
    country: str | None = None
    status: str = "active"
    event_id: str | None = None


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    supplier_id: str = Field(min_length=1, max_length=128)
    event_id: str | None = None
    delivery_delay_days: float = Field(default=0, ge=0)
    defect_rate: float = Field(default=0, ge=0, le=1)
    financial_health: float = Field(default=1, ge=0, le=1)
    geopolitical_risk: float = Field(default=0, ge=0, le=1)
    weather_risk: float = Field(default=0, ge=0, le=1)
    telemetry: dict[str, float] = Field(default_factory=dict)
    observed_at: datetime | None = None



class RiskReason(BaseModel):
    code: str
    reason: str
    points: float
    severity: str


class RiskResponse(BaseModel):
    supplier_id: str
    score: float = Field(ge=0, le=100)
    level: str
    reasons: list[RiskReason]
    abnormal_telemetry: list[str] = Field(default_factory=list)
    calculated_at: datetime
    duplicate: bool = False


class Disruption(BaseModel):
    model_config = ConfigDict(extra="allow")
    supplier_id: str = Field(min_length=1, max_length=128)
    event_id: str | None = None
    disruption_type: str = Field(min_length=1, max_length=80)
    severity: str = "medium"
    message: str = Field(min_length=1, max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class TelemetryRequest(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=128)
    event_id: str | None = None
    values: dict[str, float] = Field(min_length=1)
    observed_at: datetime | None = None


# Kept here for compatibility with the original graph query API.
class DependencyNode(BaseModel):
    company_id: str
    name: str | None = None
    tier: int = Field(ge=1, le=5)


class DependencyResponse(BaseModel):
    root_company_id: str
    nodes: list[DependencyNode]


class BlastRadiusResponse(BaseModel):
    company_id: str
    affected_count: int = Field(ge=0)
    affected_company_ids: list[str]


class AlternativeSupplier(BaseModel):
    company_id: str
    name: str | None = None
    country: str | None = None


class AlternativeSupplierResponse(BaseModel):
    company_id: str
    alternatives: list[AlternativeSupplier]
