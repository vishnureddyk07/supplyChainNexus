CREATE TABLE disruption_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    supplier_id UUID NOT NULL
        REFERENCES suppliers(id)
        ON DELETE CASCADE,

    disruption_type TEXT NOT NULL,

    severity TEXT NOT NULL
        CHECK (severity IN ('low','medium','high','critical')),

    description TEXT,

    source TEXT,

    detected_at TIMESTAMPTZ NOT NULL,

    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_disruption_supplier
    ON disruption_log(supplier_id);

CREATE INDEX idx_disruption_detected
    ON disruption_log(detected_at);

CREATE INDEX idx_disruption_severity
    ON disruption_log(severity);

CREATE INDEX idx_disruption_unresolved
    ON disruption_log(resolved_at)
    WHERE resolved_at IS NULL;