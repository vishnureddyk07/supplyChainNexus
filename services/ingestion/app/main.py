from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException

from app.connectors import get_connector, list_connectors
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.schemas import HealthResponse


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
	settings = get_settings()
	configure_logging(settings.log_level)
	logger.info("starting ingestion service")
	yield
	logger.info("stopping ingestion service")


app = FastAPI(title="Ingestion Service", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
	settings = get_settings()
	return HealthResponse(
		service=settings.service_name,
		environment=settings.environment,
		connectors=list_connectors(),
	)


@app.post("/normalize/{source_type}")
def normalize(source_type: str, payload: dict) -> dict:
	try:
		connector = get_connector(source_type)
	except KeyError as exc:
		raise HTTPException(status_code=404, detail=str(exc)) from exc
	return connector.normalize(payload)
