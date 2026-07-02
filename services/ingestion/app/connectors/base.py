from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
	name: str
	source_type: str

	@abstractmethod
	def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
		raise NotImplementedError
