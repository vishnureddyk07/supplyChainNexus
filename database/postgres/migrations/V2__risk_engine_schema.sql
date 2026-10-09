CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY, name TEXT, country TEXT, status TEXT NOT NULL,
    event_id TEXT UNIQUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS risk_history (
    id BIGSERIAL PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    event_id TEXT, fingerprint TEXT NOT NULL UNIQUE, score NUMERIC(5,2) NOT NULL,
    level TEXT NOT NULL, reasons JSONB NOT NULL, abnormal_telemetry JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS risk_history_supplier_time
    ON risk_history(supplier_id, calculated_at DESC);
CREATE TABLE IF NOT EXISTS disruptions (
    id BIGSERIAL PRIMARY KEY, supplier_id TEXT NOT NULL, event_id TEXT,
    fingerprint TEXT NOT NULL UNIQUE, disruption_type TEXT NOT NULL,
    severity TEXT NOT NULL, message TEXT NOT NULL, starts_at TIMESTAMPTZ,
    ends_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
