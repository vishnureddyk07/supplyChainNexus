ALTER TABLE suppliers
    ALTER COLUMN domain DROP NOT NULL,
    ADD COLUMN external_id TEXT UNIQUE;

CREATE TABLE supply_chain_events (
    event_id UUID PRIMARY KEY,
    schema_version SMALLINT NOT NULL CHECK (schema_version > 0),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'sensor.telemetry',
            'supplier.created',
            'supplier.updated',
            'supplier.deleted'
        )
    ),
    source_system TEXT NOT NULL CHECK (
        source_system IN ('sensor_simulator', 'supplier_erp')
    ),
    supplier_external_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX idx_supply_chain_events_occurred_at
    ON supply_chain_events(occurred_at DESC);

CREATE INDEX idx_supply_chain_events_supplier
    ON supply_chain_events(supplier_external_id, occurred_at DESC);

CREATE INDEX idx_supply_chain_events_type
    ON supply_chain_events(event_type, occurred_at DESC);
