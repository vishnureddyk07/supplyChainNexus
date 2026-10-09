from __future__ import annotations

from pydantic import BaseModel, Field


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
