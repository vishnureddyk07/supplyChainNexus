CREATE TABLE supplier_risk_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    supplier_id UUID NOT NULL
        REFERENCES suppliers(id)
        ON DELETE CASCADE,

    risk_score NUMERIC(5,2) NOT NULL
        CHECK (risk_score >= 0 AND risk_score <= 100),

    risk_category TEXT NOT NULL
        CHECK (risk_category IN ('low','medium','high','critical')),

    score_source TEXT,

    scored_at TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_supplier_risk_supplier
    ON supplier_risk_scores(supplier_id);

CREATE INDEX idx_supplier_risk_scored_at
    ON supplier_risk_scores(scored_at);

CREATE INDEX idx_supplier_risk_latest
    ON supplier_risk_scores(supplier_id, scored_at DESC);