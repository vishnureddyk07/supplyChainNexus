# SupplyChainNexus

## Phase 1: event ingestion and persistence

Phase 1 provides a local development pipeline for simulated sensor telemetry and
supplier ERP events:

```text
sensor simulator ─┐
                  ├─ MQTT/Mosquitto → validated ingestion → Kafka
supplier ERP API ─┘                                  ↓
                                       idempotent consumer → PostgreSQL
                                                              ↓
                                                durable Neo4j projection
```

The shared versioned event contract lives in `supplychain_nexus/contracts.py`.
The ingestion service validates MQTT messages, forwards valid events to Kafka,
and puts malformed messages on a dead-letter topic before acknowledging them to
MQTT. A separate Kafka consumer writes events and supported supplier records
transactionally to PostgreSQL. PostgreSQL event IDs are primary keys, and
duplicate deliveries do not repeat supplier updates.
Pipeline services emit JSON-formatted logs with event, topic, and source
context where applicable.

The simulator and ERP mock mark generated records with
`traceability.simulated: true`. Their output is synthetic development data, not
real supplier or sensor observations.

## Local setup

Requirements: Docker Desktop with Docker Compose v2 and Python 3.11+ for local
tests.

1. From this directory, create `.env` from the example and replace the
   development placeholders:

   ```powershell
   Copy-Item .env.example .env
   ```

   If reusing a PostgreSQL or Neo4j volume initialized by the original Compose
   file, preserve its existing login values (the original local defaults were
   `postgres` / `postgres` and `neo4j` / `password`). Changing initialization
   environment variables does not change credentials stored in an existing
   data volume. For a new local volume, use new values in `.env`.

2. Build and start the local pipeline and graph services:

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

   Neo4j stores the event graph projection. Its local credentials are
   development-only. Mosquitto allows anonymous local connections; neither
   configuration is suitable for production.

3. Inspect service logs:

   ```powershell
   docker compose logs -f ingestion event-consumer supplier-erp-mock
   ```

4. Generate an ERP event. The endpoint publishes the returned event to MQTT
   before responding; it returns HTTP 503 if the broker cannot accept it:

   ```powershell
   Invoke-RestMethod http://localhost:8000/supplier-event
   Invoke-RestMethod http://localhost:8000/supplier-events/5
   ```

   Sensor telemetry is generated continuously. Change `EVENT_INTERVAL` or
   `SCENARIO_MODE` in `.env` (`normal`, `warning`, or the severe scenario) and
   recreate the simulator with `docker compose up -d --force-recreate
   sensor-simulator` to apply changes.

5. Inspect persisted events and suppliers:

   ```powershell
   docker compose exec postgres psql -U postgres -d supplychain -c "SELECT event_id, event_type, source_system, supplier_external_id, occurred_at, received_at FROM supply_chain_events ORDER BY received_at DESC LIMIT 20;"
   docker compose exec postgres psql -U postgres -d supplychain -c "SELECT id, external_id, name, domain, metadata FROM suppliers ORDER BY updated_at DESC LIMIT 20;"
   ```

   These inspection commands use the original local database user and name.
   If those were changed in `.env`, substitute the configured values.

## Event contract

Each event has a UUID `event_id`, `schema_version: 1`, a timezone-aware
`timestamp`, `event_type`, `supplier_id`, `source_system`, and optional
`shipment_id`, `facility_id`, and traceability metadata. Sensor telemetry
requires `sensor_measurements` and is sourced from `sensor_simulator`. Supplier
lifecycle events require `supplier_data` and are sourced from `supplier_erp`.
Unexpected fields, unknown event types, invalid timestamps, and invalid
measurement values are rejected.

Example sensor event:

```json
{
  "event_id": "fcb6b5df-f053-43c7-b916-287f941a90c2",
  "schema_version": 1,
  "event_type": "sensor.telemetry",
  "timestamp": "2026-10-24T08:00:00+00:00",
  "supplier_id": "supplier-001",
  "source_system": "sensor_simulator",
  "sensor_measurements": {
    "temperature": 24.2,
    "humidity": 51.0
  },
  "traceability": {
    "simulated": true
  }
}
```

Example supplier event:

```json
{
  "event_id": "d2edbde4-659c-42ba-9ce4-31d2ce3f2d12",
  "schema_version": 1,
  "event_type": "supplier.updated",
  "timestamp": "2026-10-24T08:00:00+00:00",
  "supplier_id": "supplier-erp-id",
  "source_system": "supplier_erp",
  "supplier_data": {
    "name": "Example Supplier",
    "contact_email": "operations@example.test",
    "phone": "555-0100",
    "country": "Exampleland",
    "status": "ACTIVE"
  },
  "traceability": {
    "simulated": true
  }
}
```

For compatibility, ingestion still normalizes the original flat sensor
payload and ERP event payload. Legacy sensor records without an event ID receive
a deterministic ID from their complete payload; newly generated records
already contain unique IDs.

## Topics and network addresses

Topic names are centralized in `supplychain_nexus/topics.py`:

| Purpose | Topic |
|---|---|
| Valid version-1 events | `supplychain.events.v1` |
| Invalid MQTT or Kafka events | `supplychain.events.v1.dlq` |
| Sensor MQTT input | `suppliers/{supplier_id}/telemetry` |
| ERP MQTT input | `suppliers/{supplier_id}/events` |

Containers connect to Kafka using `kafka:29092`. Host applications use
`localhost:9092` by default. The broker advertises distinct internal and host
listeners; set `KAFKA_ADVERTISED_HOST` when host clients must connect through a
non-local address. The host ports and connection variables can be changed in
`.env`; internal service addresses remain Compose DNS names.

| Service | Container address | Default host port |
|---|---|---:|
| PostgreSQL | `postgres:5432` | 5432 |
| Kafka | `kafka:29092` | 9092 |
| Mosquitto | `mosquitto:1883` | 1883 |
| ERP mock | `supplier-erp-mock:8000` | 8000 |
| Neo4j HTTP / Bolt | `neo4j:7474` / `neo4j:7687` | 7474 / 7687 |
| Application API | `application-api:8001` | 8001 |
| Frontend | `frontend:5173` | 5173 |

## Configuration and persistence

Compose settings and local-only defaults are listed in `.env.example`.
Database passwords, Neo4j credentials, and host ports are environment
configurable; do not use the sample values in a shared or production
environment. Protect the local `.env` file and provide production secrets
through a managed secret mechanism. PostgreSQL connection passwords containing
URI-reserved characters must be URL-encoded in `DATABASE_URL`.

Flyway applies migrations from `database/postgres/migrations`. V1–V4 are
preserved; V5 adds the event table and a unique external supplier identifier;
V6 adds durable graph-projection checkpoints.
`supply_chain_events.event_id` is the database idempotency constraint. Supplier
upserts occur in the same database transaction and only when a new event ID is
inserted. Processing is at-least-once, not exactly-once: Kafka offsets are
committed after database writes; a replay is made safe by the event primary
key.

The MQTT ingestion subscriber uses QoS 1 and manual acknowledgements. It only
acknowledges after Kafka delivery succeeds, or after an invalid payload is
successfully forwarded to the dead-letter topic. The consumer retries database
and dead-letter failures without committing affected offsets. The Kafka
producer uses broker acknowledgements and bounded in-client retries; the
consumer also waits for broker readiness at startup. Failed container startup
is surfaced and retried by Compose's restart policy.
The simulator and ERP API wait for the ingestion container's MQTT subscription
health check before starting, avoiding event publication before a fresh
subscription is established.

## Tests

Install test and runtime dependencies, then run unit tests and lint:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m flake8 services supplychain_nexus supplier-erp-mock tests
```

The real MQTT → Kafka → PostgreSQL → Neo4j checks are opt-in and require the
Compose stack to be running. They cover sensor and ERP events independently
and publish the same sensor event twice to check database deduplication:

```powershell
$env:RUN_PIPELINE_INTEGRATION = "1"
python -m pytest tests/integration -q
Remove-Item Env:RUN_PIPELINE_INTEGRATION
```

When connecting from the host with non-default ports or database credentials,
set `MQTT_HOST`, `MQTT_PORT`, `ERP_URL`, and `DATABASE_URL` before running the
integration tests. The integration suite skips with an explicit reason unless
`RUN_PIPELINE_INTEGRATION=1` is set; a skipped integration test is not evidence
that the live pipeline works.

## Phase 2: graph projection and risk-model foundations

The event consumer now writes each persisted event to Neo4j before committing
its Kafka offset. Startup backfills PostgreSQL events that do not have a graph
checkpoint. Event, supplier, facility, and shipment nodes are merged by stable
identifiers; only relationships supported by ingested IDs are created. The
current event-to-supplier relationship is `HAS_EVENT`. The graph does not infer
`SUPPLIES` dependency edges, and its readiness response explicitly reports
whether any such facts are known. A failed graph write prevents the Kafka
offset commit and is retried; replay remains at-least-once and idempotent.

`services/risk/features.py` builds time-bounded supplier feature snapshots.
Historical risk training uses only explicitly configured `score_source`
values (default `manual,audited`) and excludes events at the score timestamp
and later to avoid target leakage. The Random Forest trainer requires at least
30 labeled snapshots and two risk categories. Its CLI evaluates a temporal
holdout before training and saves artifacts with `skops`; loading rejects
unrecognized artifact types. Train with:

```powershell
python -m pip install -r requirements-risk.txt
$env:DATABASE_URL = "postgresql://<user>:<password>@localhost:5432/<database>"
$env:SUPPLIER_RISK_LABEL_SOURCES = "manual,audited"
python -m services.risk.train_supplier_model
```

No synthetic labels are inserted into the operational PostgreSQL database.
The separate opt-in demo profile writes clearly marked synthetic labels to its
own database and model-artifact volume. The operational supplier model remains
unavailable until trusted historical labels are supplied. Any model trained
on test fixtures or demo data must be marked `development_model=True`; those
metrics are not operational performance claims.

`services/risk/shipment_model.py` provides LightGBM training, prediction,
temporal holdout metrics against a median baseline, and native booster
artifacts. Training examples require an actual delay label recorded after the
forecast feature timestamp. The current PostgreSQL migrations do not define
shipment outcomes, so no shipment model can be trained from this database yet.
Add a verified shipment outcome data source before treating this model as
operational.

`services/risk/explainability.py` uses SHAP `TreeExplainer` for trained
Random Forest and LightGBM models. Missing numeric fields are median-imputed
and accompanied by explicit missingness indicators. The composite scorer in
`services/risk/composite.py` reports component values, weighted contributions,
coverage, missing signals, and version. It is a configurable heuristic, not a
calibrated probability; below the configured coverage threshold, severity is
`unknown` and score is null.

Risk-model packages are isolated in `requirements-risk.txt`; pipeline
containers do not install them. The application API now serves model
readiness, feature snapshots, composite heuristic assessments, predictions,
and SHAP explanations when loadable model artifacts are present. V8 adds a
shipment-outcome table with coordinate/time constraints and a simulation
marker; operational training excludes simulated records. The operational
database still needs trusted risk labels and verified shipment outcomes before
operational models can be trained.

Configuration for local models and scoring is in `.env.example`:
`SUPPLIER_RISK_LABEL_SOURCES`, `SUPPLIER_RISK_MODEL_PATH`,
`COMPOSITE_RISK_VERSION`, `COMPOSITE_RISK_MINIMUM_COVERAGE`,
`SHIPMENT_DELAY_RISK_HORIZON_HOURS`, and `COMPOSITE_RISK_WEIGHTS`.
The default composite weights are explicit heuristics and should be reviewed
and versioned before use in operational decisions. Host-side Python commands
read process environment variables; export any scoring/model settings needed
in PowerShell rather than assuming Compose's `.env` file is loaded by Python.

The full local stack and Phase 1/2 checks are started as documented above.
After the containers are ready, validate the graph-projection end-to-end tests
with:

```powershell
$env:RUN_PIPELINE_INTEGRATION = "1"
python -m pytest tests/integration -q
Remove-Item Env:RUN_PIPELINE_INTEGRATION
```

The integration tests query both PostgreSQL and Neo4j for sensor and ERP
events, including duplicate event handling. They require the Flyway V6
migration to have completed and the local Neo4j credentials/ports to match
`.env`.

## Phase 3: application API and control tower

The FastAPI application at `services/application_api` serves the persisted
pipeline data and existing graph/risk foundations. The React, TypeScript, and
Vite client is in `frontend`. The Compose services are `application-api` and
`frontend`; open the dashboard at `http://localhost:5173` and the API at
`http://localhost:8001`. The API health probe is `GET /health`; interactive
OpenAPI documentation is available at `http://localhost:8001/docs`.

Before starting the application services against an existing database, apply
the additive incident/shipment migrations. This does not reset database
volumes or rewrite prior migrations:

```powershell
docker compose run --rm flyway
docker compose up --build -d
docker compose ps
```

The application service waits for PostgreSQL, successful Flyway completion,
and Neo4j health. Frontend requests use the host API URL configured through
`VITE_API_BASE_URL`. The default host ports are in the table above, with the
API on 8001 and frontend on 5173.

Protected `/api/v1` read routes accept bearer tokens. Configure distinct
`API_VIEWER_TOKEN`, `API_OPERATOR_TOKEN`, and `API_ADMIN_TOKEN` values in the
local `.env`; incident creation and updates require operator or admin access.
The legacy `API_AUTH_TOKEN` is treated as admin. If all tokens are unset, the
API explicitly reports local unauthenticated development mode. This is not
production authentication. Restrict CORS with `CORS_ORIGINS`, configure
production-grade authentication and TLS at the deployment boundary, and use
managed secrets before any shared deployment.

Available API route groups:

| Route | Purpose |
|---|---|
| `GET /api/v1/health` | API, PostgreSQL, Neo4j, and auth readiness |
| `GET /api/v1/dashboard` | Persisted KPIs, event activity, incidents, and readiness |
| `GET /api/v1/suppliers` and `/suppliers/{id}` | Supplier records, observed event-only identities, features, risk assessment, and available graph data |
| `GET /api/v1/events` and `/suppliers/{id}/events` | Filtered, paginated persisted events |
| `GET /api/v1/shipments`, `/shipments/{id}`, and `/shipments/{id}/prediction` | Persisted shipment details; predictions only with a trained artifact |
| `GET /api/v1/graph` and `/graph/suppliers/{id}/dependencies` | Neo4j entities and recorded relationship exploration |
| `GET /api/v1/models/readiness` | Risk and delay model readiness |
| `GET`, `POST /api/v1/incidents`; `PATCH /api/v1/incidents/{id}` | Persisted incident investigation tracking |
| `POST /api/v1/recommendations` | Evidence-scoped Azure OpenAI suggestions, or explicit unavailable state |

The frontend has executive overview, supplier intelligence, shipment
monitoring, knowledge graph, risk and explainability, event monitor, incident
management, and AI recommendation views. It polls dashboard data every 15
seconds; this is polling, not a WebSocket or a guaranteed real-time feed.
Graph nodes/edges come from Neo4j only. Supplier/event totals and incident
records come from PostgreSQL.

Trained model artifacts are stored in the Compose `model_artifacts` volume and
mounted into the API container. Once trusted risk labels exist, the supplier
model can be trained against the Compose database with:

```powershell
docker compose exec application-api python -m services.risk.train_supplier_model
```

Do not train or report operational metrics from simulated events or test
fixtures. The current database has no trusted labels, so that command is not
expected to produce an operational model yet.

There are currently no verified shipment outcomes or trusted risk labels in
the live data. Shipment listings therefore remain empty, delay predictions
remain unavailable, and no calibrated model prediction or accuracy is shown.
Heuristic composite assessments remain labelled as heuristics; SHAP details
are returned only if a trained, loadable model artifact exists. Azure
recommendations require `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and
`AZURE_OPENAI_DEPLOYMENT`; when those are unset, the API returns an unavailable
status rather than generated text.

## Isolated synthetic demonstration profile

Use the Compose `demo` profile to demonstrate supplier risk classification,
shipment delay estimation, map rendering, recorded dependency exploration, and
incident tracking without writing synthetic labels or shipment outcomes to the
operational PostgreSQL/Neo4j volumes. The profile creates separate
`demo_postgres_data`, `demo_neo4j_data`, and `demo_model_artifacts` volumes; it
does not reset or delete any volume.

The generator is deterministic for the current UTC date. It marks its events,
shipment records, supplier labels, graph dependencies, and incident as
simulated. The model trainer opts in to those synthetic labels only inside the
demo profile, evaluates against temporal holdouts, and writes separate model
artifacts and evaluation metadata. Metrics and predictions from this profile
are development demonstrations, not operational performance evidence.

```powershell
# Start/rebuild the regular stack plus the isolated demo workspace
docker compose --profile demo up --build -d
docker compose --profile demo ps

# Demo dashboard/API
Start-Process http://localhost:5174
Invoke-RestMethod http://localhost:8002/health

# Inspect the isolated demo database
docker compose exec demo-postgres psql -U supplychain_demo -d supplychain_demo -c "SELECT count(*) AS events FROM supply_chain_events;"
docker compose exec demo-postgres psql -U supplychain_demo -d supplychain_demo -c "SELECT count(*) AS shipments, count(*) FILTER (WHERE simulated) AS synthetic FROM shipments;"
docker compose logs demo-seed demo-model-trainer demo-event-consumer demo-api demo-frontend
```

The demo consumer reads the shared Kafka topic using a separate consumer group
and accepts only records whose Kafka key begins `demo-supplier-`; it will not
copy operational supplier events into the isolated demo store. The deterministic
scenario is initially seeded directly through the validated event model and
PostgreSQL/Neo4j repositories; this bootstrap does not claim to be an MQTT-to-
Kafka end-to-end demo replay. The regular sensor/ERP pipeline remains available
and independently testable on its existing services.

Run the isolated demo integration check after the profile is healthy:

```powershell
$env:RUN_DEMO_INTEGRATION = "1"
python -m pytest tests/integration/test_demo_application_e2e.py -q
Remove-Item Env:RUN_DEMO_INTEGRATION
```

To stop the demo containers without deleting their persisted data:

```powershell
docker compose --profile demo down
```

Do not use `down -v` if you want to retain either environment's data. The demo
uses a separate Neo4j password setting (`DEMO_NEO4J_PASSWORD`) and PostgreSQL
credentials (`DEMO_POSTGRES_USER`, `DEMO_POSTGRES_PASSWORD`, and
`DEMO_POSTGRES_DB`). Replace local placeholders before sharing access.

Flyway V8 creates the shipments table and coordinate/time constraints; V9
adds the incident simulation marker and idempotency index for demo risk labels;
V10 adds simulation provenance to disruption records. Existing migrations are
preserved and applied additively to the relevant database.

Production API startup can be explicitly selected with `APP_ENV=production`.
It fails closed unless distinct viewer/operator/admin tokens of at least 32
characters and explicit HTTPS-only origin URLs (scheme and host, no wildcard
or path) are configured. Generate tokens with a cryptographically secure secret
manager. Local Compose defaults remain for development only and must not be
treated as production credentials or a production-ready deployment.

Run the application checks:

```powershell
python -m pytest tests/test_application_api.py -q
Set-Location frontend
npm ci
npm run typecheck
npm run build
Set-Location ..
```

The application end-to-end checks exercise the live API, Neo4j, and persisted
incident create/update path. They are opt-in and remove only the uniquely
identified incident they create:

```powershell
$env:RUN_APPLICATION_INTEGRATION = "1"
python -m pytest tests/integration/test_application_api_e2e.py -q
Remove-Item Env:RUN_APPLICATION_INTEGRATION
```

Use the same database credentials and host ports configured in `.env` when
setting `DATABASE_URL`, `API_TEST_TOKEN`, or `APPLICATION_API_URL` for host-run
integration tests. A skipped integration test is not evidence of a working
live connection.

## Current limitations

- The event producer and consumer use a single local Kafka broker. This is a
  development topology, not a highly available deployment.
- The dead-letter topic is configured by name and relies on Kafka's local
  automatic topic creation; production deployments should provision it and set
  retention/alerting explicitly.
- Sensor events contain measurements and supplier identifiers only; the
  simulator does not invent supplier identity, shipment, or facility details.
- The ERP mock is synthetic and publishes when its endpoints are called. It is
  not an integration with a real ERP.
- Incident persistence uses additive migration V7; V9 only adds an explicit
  simulation marker. Existing migrations are not rewritten.
- Operational supplier risk training still requires trusted risk-score labels;
  operational shipment-delay training still requires verified shipment
  outcomes. The separately isolated demo contains synthetic labels/outcomes and
  must not be interpreted as production evidence.
- The operational graph contains only recorded entities and relationships.
  Synthetic demo dependencies and routes are isolated and explicitly marked;
  no operational supplier dependencies or shipment coordinates are invented.
- The frontend polls instead of consuming WebSockets. Incident ownership and
  investigation notes are supported, but there is no separate workflow engine.
- Azure integration cannot be runtime-verified without configured endpoint,
  deployment, and credentials.
- Authentication defaults to unauthenticated local development when no tokens
  are configured. This Compose stack, broker, database, and graph configuration
  are not a production security or high-availability deployment.
