"""Run the source connectors and publish validated events to Kafka."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Response

from .connectors import GdeltConnector, MarineTrafficConnector, MqttIotConnector, OpenWeatherConnector, SupplierErpConnector
from .publisher import KafkaEventPublisher
from .schema_validation import AvroSchemaValidator


def create_app(publisher: KafkaEventPublisher | None = None) -> FastAPI:
    service = FastAPI(title="Supply Chain Ingestion")
    service.state.publisher = publisher
    service.state.schema_validator = publisher.validator if publisher else AvroSchemaValidator()

    @service.get("/health")
    async def health() -> dict[str, object]:
        configured_publisher = service.state.publisher
        kafka_ready = configured_publisher is not None and getattr(configured_publisher, "_producer", None) is not None
        schema_ready = service.state.schema_validator.check()
        healthy = kafka_ready and schema_ready
        return {
            "status": "ok" if healthy else "degraded",
            "dependencies": {"kafka": kafka_ready, "schema_registry": schema_ready},
        }

    @service.get("/metrics")
    async def metrics_endpoint() -> Response:
        from .metrics import metrics

        return Response(content=metrics.prometheus(), media_type="text/plain; version=0.0.4")

    return service


app = create_app()


def configure_logging() -> None:
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            fields = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            for key in ("source", "topic", "error", "url", "attempt", "delay", "count", "broker"):
                if hasattr(record, key):
                    fields[key] = getattr(record, key)
            return json.dumps(fields, default=str)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(JsonFormatter())


async def main() -> None:
    configure_logging()
    publisher = KafkaEventPublisher(os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"))
    app.state.publisher = publisher
    app.state.schema_validator = publisher.validator
    await publisher.start()
    stop = asyncio.Event()
    mqtt_connector = MqttIotConnector(publisher)
    mqtt_connector.start(asyncio.get_running_loop())
    connectors = [
        MarineTrafficConnector(publisher),
        OpenWeatherConnector(publisher),
        GdeltConnector(publisher),
        SupplierErpConnector(publisher),
    ]
    tasks = [asyncio.create_task(connector.run(stop)) for connector in connectors]
    try:
        import uvicorn

        server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("INGESTION_PORT", "8080")), log_config=None))
        await asyncio.gather(*(tasks + [server.serve()]))
    finally:
        stop.set()
        mqtt_connector.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for connector in connectors:
            await connector.close()
        await publisher.stop()


if __name__ == "__main__":
    asyncio.run(main())
