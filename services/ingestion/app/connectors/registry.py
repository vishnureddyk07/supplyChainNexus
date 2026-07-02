from __future__ import annotations

from typing import Type

from app.connectors.base import BaseConnector

_CONNECTORS: dict[str, Type[BaseConnector]] = {}


def register_connector(connector_cls: Type[BaseConnector]) -> Type[BaseConnector]:
	_CONNECTORS[connector_cls.source_type] = connector_cls
	return connector_cls


def get_connector(source_type: str) -> BaseConnector:
	connector_cls = _CONNECTORS.get(source_type)
	if connector_cls is None:
		raise KeyError(f"No connector registered for source_type={source_type}")
	return connector_cls()


def list_connectors() -> list[str]:
	return sorted(_CONNECTORS.keys())
