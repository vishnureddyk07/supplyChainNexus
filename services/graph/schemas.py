from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GraphEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    identifier: str = Field(min_length=1)
    properties: dict[str, Any]


class GraphRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_label: str
    source_id: str = Field(min_length=1)
    relationship_type: str
    target_label: str
    target_id: str = Field(min_length=1)


class SupplierGraphView(BaseModel):
    supplier_id: str
    supplier: dict[str, Any]
    events: list[dict[str, Any]]
    facilities: list[dict[str, Any]]
    shipments: list[dict[str, Any]]
    retrieved_at: datetime


class DependencyPath(BaseModel):
    supplier_ids: list[str]
    hop_count: int = Field(ge=1)


class GraphReadiness(BaseModel):
    ready: bool
    node_counts: dict[str, int]
    relationship_counts: dict[str, int]
    note: str | None = None
