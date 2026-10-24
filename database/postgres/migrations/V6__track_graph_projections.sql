CREATE TABLE graph_projection_state (
    event_id UUID PRIMARY KEY
        REFERENCES supply_chain_events(event_id)
        ON DELETE CASCADE,
    projected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_graph_projection_projected_at
    ON graph_projection_state(projected_at DESC);
