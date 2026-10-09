"""Avro payload validation and Schema Registry configuration."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .events import TOPICS

LOGGER = logging.getLogger("ingestion.schema")
SCHEMA_DIR = Path(__file__).with_name("schemas")


def schema_registry_url() -> str:
    environment = os.getenv("INGESTION_ENV", os.getenv("APP_ENV", "local")).lower()
    configured = os.getenv("SCHEMA_REGISTRY_URL")
    if configured:
        return configured
    return {
        "local": "http://localhost:8081",
        "dev": "http://schema-registry-dev:8081",
        "development": "http://schema-registry-dev:8081",
        "prod": "http://schema-registry:8081",
        "production": "http://schema-registry:8081",
    }.get(environment, "http://localhost:8081")


class SchemaValidationError(ValueError):
    """Raised when an event payload does not match its raw-domain schema."""


class AvroSchemaValidator:
    def __init__(self, registry_url: str | None = None) -> None:
        self.registry_url = registry_url or schema_registry_url()
        self.registry_available = False
        self._registry_checked = False
        self._registry = None
        try:
            from confluent_kafka.schema_registry import SchemaRegistryClient

            self._registry = SchemaRegistryClient({"url": self.registry_url})
        except ImportError as exc:
            LOGGER.warning("schema_registry_client_unavailable", extra={"error": str(exc)})

    def validate(self, source: str, payload: dict[str, Any]) -> None:
        if source not in TOPICS:
            raise SchemaValidationError(f"unsupported schema source: {source}")
        schema_path = SCHEMA_DIR / f"{source}.avsc"
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            from fastavro.validation import validate

            validate(payload, schema, strict=True)
        except (OSError, json.JSONDecodeError) as exc:
            raise SchemaValidationError(f"schema could not be loaded for {source}: {exc}") from exc
        except Exception as exc:
            raise SchemaValidationError(f"{source} payload does not match Avro schema: {exc}") from exc

    def check(self) -> bool:
        if os.getenv("SCHEMA_REGISTRY_REQUIRED", "false").lower() != "true":
            return True
        if not self._registry_checked and self._registry is not None:
            try:
                self.registry_available = bool(self._registry.get_subjects())
            except Exception as exc:
                LOGGER.warning("schema_registry_unavailable", extra={"error": str(exc), "url": self.registry_url})
            self._registry_checked = True
        return self.registry_available
