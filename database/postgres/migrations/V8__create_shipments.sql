CREATE TABLE shipments (
    shipment_id TEXT PRIMARY KEY CHECK (length(trim(shipment_id)) > 0),
    supplier_external_id TEXT NOT NULL,
    origin_name TEXT NOT NULL,
    origin_latitude DOUBLE PRECISION NOT NULL
        CHECK (origin_latitude BETWEEN -90 AND 90),
    origin_longitude DOUBLE PRECISION NOT NULL
        CHECK (origin_longitude BETWEEN -180 AND 180),
    destination_name TEXT NOT NULL,
    destination_latitude DOUBLE PRECISION NOT NULL
        CHECK (destination_latitude BETWEEN -90 AND 90),
    destination_longitude DOUBLE PRECISION NOT NULL
        CHECK (destination_longitude BETWEEN -180 AND 180),
    planned_departure TIMESTAMPTZ NOT NULL,
    planned_arrival TIMESTAMPTZ NOT NULL,
    actual_arrival TIMESTAMPTZ,
    simulated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (planned_arrival > planned_departure)
);

CREATE INDEX idx_shipments_supplier_departure
    ON shipments(supplier_external_id, planned_departure DESC);
CREATE INDEX idx_shipments_route_arrival
    ON shipments(origin_name, destination_name, actual_arrival)
    WHERE actual_arrival IS NOT NULL;
CREATE INDEX idx_shipments_planned_departure
    ON shipments(planned_departure DESC);

CREATE TRIGGER trg_shipments_updated_at
BEFORE UPDATE ON shipments
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
