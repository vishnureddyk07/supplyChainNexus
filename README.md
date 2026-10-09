# Supply Chain Nexus

Supply Chain Nexus is a local, Docker Compose demonstration for ingesting
supplier telemetry and external supplier events, calculating explainable risk,
and reviewing results in a responsive dashboard.

## Architecture

```text
sensor simulator --MQTT--> ingestion --Kafka--> graph/event persistence
supplier ERP mock --------HTTP----> ingestion       |       |
                                                   Neo4j  PostgreSQL
                                                     \     /
                                                   risk engine
                                                       |
                                                React dashboard
```

The ingestion and graph services use Kafka topics such as `raw.iot` and
`raw.supplier_erp`. PostgreSQL migrations are applied by Flyway. Named Docker
volumes preserve PostgreSQL, Neo4j, and Valkey data across normal restarts.

## Run locally

Requirements: Docker Desktop with Compose v2.

```powershell
docker compose up -d --build
docker compose ps
```

Open the dashboard at <http://localhost:3000>.

To stop containers without deleting data:

```powershell
docker compose down
```

Do not use `docker compose down -v` unless you intentionally want to delete
the local database volumes.

## Services and endpoints

| Service | URL |
| --- | --- |
| Dashboard | http://localhost:3000 |
| Ingestion health | http://localhost:8080/health |
| Backend health | http://localhost:8001/health |
| Graph health | http://localhost:8002/health |
| Risk engine health | http://localhost:8090/health |
| GenAI engine health | http://localhost:8091/health |
| Neo4j browser | http://localhost:7474 |

Risk engine API:

- `GET /suppliers` and `GET /suppliers/{supplier_id}`
- `POST /suppliers`
- `POST /risk/score`, `GET /risk/{supplier_id}`, and
  `GET /risk/{supplier_id}/history`
- `POST /telemetry`
- `GET /disruptions` and `POST /disruptions`

Risk scores are deterministic and range from 0 to 100. Levels are `low`
(0-24), `medium` (25-49), `high` (50-74), and `critical` (75-100).
Reasons include the contributing rules and values so a score is explainable.

## Configuration

Copy `.env.example` when overriding local defaults. Important variables include:

- `DATABASE_URL` (Compose default: `postgresql://postgres:postgres@postgres:5432/supplychain`)
- `KAFKA_BOOTSTRAP_SERVERS` (Compose services use `kafka:29092`)
- `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
- `SUPPLIER_ERP_URL`
- `VITE_API_URL` for the frontend build (defaults to `http://localhost:8090`)

## Development checks

```powershell
python -m pip install -r services/ingestion/requirements.txt
python -m pytest
docker compose config --quiet
```

The frontend can be built independently:

```powershell
Set-Location frontend
npm ci
npm run build
```

## Baseline prediction pipeline

`scripts/ml_baseline.py` contains a reproducible, dependency-light logistic
baseline using explicitly **synthetic** labelled examples. It combines
telemetry anomalies, delay hours, and incident counts, and reports accuracy,
precision, recall, and F1. It is a demonstration baseline, not a production
model; replace `SYNTHETIC_DATASET` with historical labelled data before using
it for operational decisions.

```powershell
python scripts/ml_baseline.py
```

## Demo flow

1. Start Compose and wait for the health checks to become healthy.
2. Open the dashboard and choose a risk-level filter.
3. Query `/suppliers` and `/disruptions` to inspect live service data.
4. Submit a telemetry event to `POST /telemetry` and inspect the returned score.
5. Run `python -m pytest` to verify ingestion, risk, and baseline tests.
