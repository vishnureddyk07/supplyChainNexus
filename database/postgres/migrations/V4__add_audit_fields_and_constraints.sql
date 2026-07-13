
ALTER TABLE suppliers
ADD COLUMN IF NOT EXISTS created_by TEXT,
ADD COLUMN IF NOT EXISTS updated_by TEXT;

ALTER TABLE supplier_risk_scores
ADD COLUMN IF NOT EXISTS created_by TEXT,
ADD COLUMN IF NOT EXISTS updated_by TEXT;

ALTER TABLE disruption_log
ADD COLUMN IF NOT EXISTS created_by TEXT,
ADD COLUMN IF NOT EXISTS updated_by TEXT;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
	NEW.updated_at = NOW();
	RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_suppliers_updated_at
BEFORE UPDATE ON suppliers
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_supplier_risk_updated_at
BEFORE UPDATE ON supplier_risk_scores
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_disruption_updated_at
BEFORE UPDATE ON disruption_log
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
