from __future__ import annotations

import json
import os
from pathlib import Path

from services.risk.supplier_model import (
    SupplierRiskModel,
    SupplierRiskTrainingRepository,
)


def main() -> None:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required to train the supplier risk model")
    sources = tuple(
        value.strip()
        for value in os.getenv(
            "SUPPLIER_RISK_LABEL_SOURCES", "manual,audited"
        ).split(",")
        if value.strip()
    )
    repository = SupplierRiskTrainingRepository(dsn, label_sources=sources)
    examples = repository.load_examples()
    readiness = repository.readiness(examples=examples)
    if not readiness.ready:
        print(json.dumps(readiness.model_dump(mode="json"), indent=2))
        raise SystemExit(2)

    development_data = os.getenv("SUPPLIER_RISK_DEVELOPMENT_DATA", "").lower() == "true"
    evaluation = SupplierRiskModel().evaluate_temporal(
        examples,
        development_data=development_data,
    )
    model = SupplierRiskModel()
    model.fit(examples, development_model=development_data)
    artifact = Path(
        os.getenv(
            "SUPPLIER_RISK_MODEL_PATH",
            "model-artifacts/supplier-risk-rf.skops",
        )
    )
    model.save(artifact)
    result = {
        "readiness": readiness.model_dump(mode="json"),
        "temporal_evaluation": evaluation.model_dump(mode="json"),
        "model_version": model.model_version,
        "training_sample_count": model.training_sample_count,
        "development_model": model.development_model,
        "artifact_path": str(artifact),
    }
    artifact.with_suffix(artifact.suffix + ".evaluation.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
