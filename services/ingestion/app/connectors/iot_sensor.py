from typing import Any
from uuid import uuid4

from app.connectors.base import BaseConnector
from app.connectors.registry import register_connector


@register_connector
class IoTSensorConnector(BaseConnector):
	name = "iot-sensor"
	source_type = "iot_sensor"

	def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
		return {
			"event_id": str(uuid4()),
			"event_type": "telemetry.received",
			"event_version": "1.0",
			"schema_version": "1.0",
			"source": self.source_type,
			"entity_type": str(payload.get("entity_type", "asset")),
			"entity_id": str(payload.get("entity_id", "unknown")),
			"correlation_id": str(payload.get("correlation_id", uuid4())),
			"causation_id": str(payload.get("causation_id", uuid4())),
			"trace_id": str(payload.get("trace_id", uuid4())),
			"payload": payload,
			"metadata": {"connector": self.name},
			"status": "normalized",
		}
