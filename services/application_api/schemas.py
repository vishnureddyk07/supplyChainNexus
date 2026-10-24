from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    severity: Severity
    status: IncidentStatus = IncidentStatus.OPEN
    owner: str | None = Field(default=None, max_length=200)
    supplier_external_id: str | None = Field(default=None, max_length=200)
    event_id: UUID | None = None
    investigation_notes: str = Field(default="", max_length=20000)

    @field_validator("title", "description", "owner", "investigation_notes")
    @classmethod
    def strip_strings(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("title", "description")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be blank")
        return value


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    severity: Severity | None = None
    status: IncidentStatus | None = None
    owner: str | None = Field(default=None, max_length=200)
    investigation_notes: str | None = Field(default=None, max_length=20000)

    @field_validator(
        "title",
        "description",
        "owner",
        "investigation_notes",
    )
    @classmethod
    def strip_optional_strings(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("title", "description")
    @classmethod
    def reject_blank_values(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("value must not be blank")
        return value


class Page(BaseModel):
    items: list[dict]
    page: int
    page_size: int
    total: int


class GraphPayload(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    dependency_relationships_available: bool


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str | None = Field(default=None, max_length=200)
    event_id: UUID | None = None
    question: str = Field(default="Summarize operational concerns and suggest next steps.", max_length=1000)

    @field_validator("supplier_id", "question")
    @classmethod
    def trim_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class RecommendationResponse(BaseModel):
    available: bool
    generated: bool
    model: str | None = None
    recommendation: str | None = None
    evidence: list[str]
    uncertainty: list[str]
    reason: str | None = None
