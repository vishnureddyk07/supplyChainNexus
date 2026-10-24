ALTER TABLE incidents
    ADD COLUMN simulated BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX idx_demo_risk_score_idempotency
    ON supplier_risk_scores(supplier_id, scored_at)
    WHERE score_source = 'demo_synthetic';
