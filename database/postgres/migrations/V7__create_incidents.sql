CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    description TEXT NOT NULL CHECK (length(trim(description)) BETWEEN 1 AND 10000),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'investigating', 'mitigating', 'resolved')),
    owner TEXT CHECK (owner IS NULL OR length(owner) <= 200),
    supplier_external_id TEXT,
    event_id UUID REFERENCES supply_chain_events(event_id) ON DELETE SET NULL,
    investigation_notes TEXT NOT NULL DEFAULT ''
        CHECK (length(investigation_notes) <= 20000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_incidents_status_updated
    ON incidents(status, updated_at DESC);
CREATE INDEX idx_incidents_supplier
    ON incidents(supplier_external_id, created_at DESC);
