# Ingestion connectors

The ingestion service publishes every accepted source record as JSON to Kafka using
the following envelope:

```json
{
  "event_id": "uuid",
  "source": "shipping|weather|supplier_erp|iot|geopolitical",
  "event_type": "source-specific type",
  "occurred_at": "ISO-8601 timestamp",
  "ingested_at": "ISO-8601 timestamp",
  "payload": {},
  "metadata": {}
}
```

| Source | Raw topic | Connector |
| --- | --- | --- |
| MarineTraffic | `raw.shipping` | Async polling with exponential retry/backoff |
| OpenWeatherMap | `raw.weather` | Concurrent location polling |
| Supplier ERP | `raw.supplier_erp` | Polls `/supplier-events/{count}` |
| IoT MQTT | `raw.iot` | Subscribes to `suppliers/+/telemetry` |
| GDELT | `raw.geopolitical` | Async news polling |

HTTP source errors are retried and logged with source context. A failed polling
cycle is logged and retried on the next schedule without stopping other sources.
Malformed MQTT messages are rejected and logged. API-key-backed sources remain
disabled when their credentials are absent; the other connectors continue to run.

Set credentials and polling configuration in `.env` using `.env.example` as the
starting point. Inside Docker, Kafka is reached at `kafka:9092` and the ERP mock
at `http://supplier-erp-mock:8000`.

## Reliability and monitoring

Every `raw.*` payload is validated against the matching Avro schema in
`services/ingestion/schemas` before it is published. A schema or processing
failure is isolated to `raw.dlq`; DLQ records include the original event,
`source`, UTC `timestamp`, `error_type`, and error text.

The ingestion service listens on port `8080` by default:

* `GET /health` reports Kafka and Schema Registry readiness. Set
  `SCHEMA_REGISTRY_REQUIRED=true` in production to fail health checks when the
  registry cannot be reached.
* `GET /metrics` exposes accepted, rejected, failed, and DLQ event counters in
  Prometheus text format.

`INGESTION_ENV` selects the default Schema Registry endpoint for `local`, `dev`,
and `prod`; `SCHEMA_REGISTRY_URL` always overrides the environment default.
