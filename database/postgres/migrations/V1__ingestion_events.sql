CREATE TABLE IF NOT EXISTS ingestion_events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    supplier_id TEXT,
    occurred_at TIMESTAMPTZ,
    payload JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ingestion_events_supplier_idx
    ON ingestion_events (supplier_id, occurred_at);

CREATE TABLE IF NOT EXISTS supplier_data (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT,
    contact_email TEXT,
    phone TEXT,
    country TEXT,
    status TEXT,
    last_event_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telemetry (
    event_id TEXT PRIMARY KEY REFERENCES ingestion_events(event_id),
    supplier_id TEXT NOT NULL,
    temperature DOUBLE PRECISION NOT NULL,
    humidity DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS telemetry_supplier_recorded_idx
    ON telemetry (supplier_id, recorded_at);
