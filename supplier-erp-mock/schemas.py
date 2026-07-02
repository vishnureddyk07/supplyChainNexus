from typing import Any, Literal

from pydantic import BaseModel, Field


class EventSource(BaseModel):
	system: str
	service: str
	environment: str


class EventEntity(BaseModel):
	type: str
	id: str


class SupplierPayload(BaseModel):
	supplier_id: str
	supplier_name: str
	contact_email: str
	phone: str
	country: str
	status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
	event_action: Literal["CREATED", "UPDATED", "DELETED"]


class CanonicalEvent(BaseModel):
	event_id: str
	event_type: Literal[
		"supplier.created",
		"supplier.updated",
		"supplier.deleted",
	]
	event_version: str = "1.0"
	schema_version: str = "1.0"
	occurred_at: str
	ingested_at: str | None = None
	source: EventSource
	entity: EventEntity
	tenant_id: str = "global"
	correlation_id: str
	causation_id: str
	trace_id: str
	payload: SupplierPayload
	metadata: dict[str, Any] = Field(default_factory=dict)
