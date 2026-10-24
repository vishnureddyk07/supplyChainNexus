from __future__ import annotations

import os

from services.risk import train_shipment_model, train_supplier_model


def main() -> None:
    if os.getenv("APP_ENV") != "development-demo":
        raise RuntimeError("demo training refuses to run outside development-demo mode")
    if os.getenv("SUPPLIER_RISK_DEVELOPMENT_DATA", "").lower() != "true":
        raise RuntimeError("demo training requires explicit synthetic-model opt-in")
    if os.getenv("SHIPMENT_MODEL_DEVELOPMENT_DATA", "").lower() != "true":
        raise RuntimeError("demo shipment training requires explicit synthetic-model opt-in")
    train_supplier_model.main()
    train_shipment_model.main()


if __name__ == "__main__":
    main()
