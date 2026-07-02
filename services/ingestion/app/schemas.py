from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
	event_id: str
	event_type: str
	event_version: str = "1.0"
	schema_version: str = "1.0"
	source: str
	entity_type: str
	entity_id: str
	correlation_id: str
	causation_id: str
	trace_id: str
	payload: dict[str, Any] = Field(default_factory=dict)
	metadata: dict[str, Any] = Field(default_factory=dict)
	status: Literal["accepted", "normalized"] = "accepted"


class HealthResponse(BaseModel):
	status: Literal["ok"] = "ok"
	service: str
	environment: str
	connectors: list[str]
