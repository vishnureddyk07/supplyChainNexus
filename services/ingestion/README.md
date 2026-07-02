# Ingestion Service

Validates incoming events, normalizes them to the canonical envelope, and publishes them to Kafka.

## Purpose

This service is the HTTP entry point for mocked and external sources. It resolves the source connector, normalizes the payload, and prepares the event for downstream delivery.

## Run Locally

```bash
cd services/ingestion
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

## Endpoints

- `GET /health` - reports service status and registered connectors.
- `POST /normalize/{source_type}` - normalizes an incoming payload using the selected connector.

## Connector Architecture

Connectors are registered in `app/connectors/registry.py` and implement the `BaseConnector` interface. To add a new integration, create a connector class, decorate it with `@register_connector`, and implement `normalize`.