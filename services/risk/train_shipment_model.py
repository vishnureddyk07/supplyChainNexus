from __future__ import annotations

import json
import os
from pathlib import Path

from services.risk.shipment_model import ShipmentDelayModel
from services.risk.shipments import ShipmentTrainingRepository


def main() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required to train the shipment delay model")
    development_data = os.getenv("SHIPMENT_MODEL_DEVELOPMENT_DATA", "").lower() == "true"
    examples = ShipmentTrainingRepository(dsn).load_examples(
        development_data=development_data,
    )
    if len(examples) < 30:
        raise SystemExit(
            json.dumps(
                {
                    "ready": False,
                    "sample_count": len(examples),
                    "reason": "At least 30 verified shipment outcomes are required.",
                },
                indent=2,
            )
        )
    evaluation = ShipmentDelayModel().evaluate_temporal(
        examples,
        development_data=development_data,
    )
    model = ShipmentDelayModel()
    model.fit(
        examples,
        development_model=development_data,
    )
    artifact = Path(
        os.getenv("SHIPMENT_DELAY_MODEL_PATH", "model-artifacts/shipment-delay.txt")
    )
    model.save(artifact)
    result = {
        "ready": True,
        "development_data": development_data,
        "temporal_evaluation": evaluation.model_dump(mode="json"),
        "training_sample_count": model.training_sample_count,
        "model_version": model.model_version,
        "artifact_path": str(artifact),
    }
    artifact.with_suffix(artifact.suffix + ".evaluation.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
