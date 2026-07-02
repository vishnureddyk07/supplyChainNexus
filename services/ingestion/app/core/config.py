from functools import lru_cache
from os import getenv


class Settings:
	def __init__(self) -> None:
		self.service_name = getenv("SERVICE_NAME", "ingestion-service")
		self.environment = getenv("ENVIRONMENT", "local")
		self.log_level = getenv("LOG_LEVEL", "INFO")
		self.default_source = getenv("DEFAULT_SOURCE", "supplier_erp")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
	return Settings()
