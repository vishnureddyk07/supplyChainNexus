from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import lightgbm as lgb
import numpy as np
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from services.risk.feature_encoding import NumericFeatureEncoder
from services.risk.schemas import (
    ModelEvaluation,
    ModelReadiness,
    ShipmentDelayPrediction,
    ShipmentFeatures,
    ShipmentDelayTrainingExample,
)


class ShipmentDelayModel:
    """LightGBM delay regressor; training requires actual, post-forecast labels."""

    def __init__(
        self,
        booster: lgb.Booster | None = None,
        encoder: NumericFeatureEncoder | None = None,
        model_version: str = "shipment-lightgbm-v1",
        development_model: bool = False,
        training_sample_count: int = 0,
    ) -> None:
        self.booster = booster
        self.encoder = encoder
        self.model_version = model_version
        self.development_model = development_model
        self.training_sample_count = training_sample_count

    @property
    def ready(self) -> bool:
        return self.booster is not None and self.encoder is not None

    @staticmethod
    def readiness(sample_count: int = 0) -> ModelReadiness:
        ready = sample_count >= 30
        return ModelReadiness(
            model_name="shipment-delay-lightgbm",
            ready=ready,
            sample_count=sample_count,
            label_source="verified actual shipment delay labels",
            reason=(
                None
                if ready
                else "At least 30 verified actual shipment-delay labels are required; "
                "the current schema has no shipment outcome table."
            ),
        )

    def fit(
        self,
        examples: Sequence[ShipmentDelayTrainingExample],
        *,
        model_version: str = "shipment-lightgbm-v1",
        development_model: bool = False,
        minimum_samples: int = 30,
    ) -> None:
        if len(examples) < minimum_samples:
            raise ValueError(
                f"at least {minimum_samples} labeled examples are required"
            )
        rows = [example.features.model_features() for example in examples]
        encoder = NumericFeatureEncoder()
        encoder.fit(rows)
        matrix = encoder.transform(rows)
        targets = np.asarray(
            [example.actual_delay_hours for example in examples], dtype=np.float64
        )
        model = lgb.LGBMRegressor(
            objective="regression",
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=5,
            random_state=42,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        model.fit(matrix, targets, feature_name=list(encoder.encoded_feature_names))
        self.booster = model.booster_
        self.encoder = encoder
        self.model_version = model_version
        self.development_model = development_model
        self.training_sample_count = len(examples)

    def predict(
        self, features: ShipmentFeatures
    ) -> ShipmentDelayPrediction:
        booster, encoder = self._require_ready()
        matrix = encoder.transform([features.model_features()])
        prediction = max(0.0, float(booster.predict(matrix)[0]))
        return ShipmentDelayPrediction(
            shipment_id=features.shipment_id,
            predicted_delay_hours=prediction,
            model_version=self.model_version,
            predicted_at=datetime.now(UTC),
            development_model=self.development_model,
        )

    def evaluate_temporal(
        self,
        examples: Sequence[ShipmentDelayTrainingExample],
        *,
        test_fraction: float = 0.2,
        development_data: bool = False,
    ) -> ModelEvaluation:
        if not 0.1 <= test_fraction <= 0.5:
            raise ValueError("test_fraction must be between 0.1 and 0.5")
        ordered = sorted(examples, key=lambda item: item.features.as_of)
        split = int(len(ordered) * (1 - test_fraction))
        train, test = ordered[:split], ordered[split:]
        if len(train) < 2 or not test:
            raise ValueError("not enough examples for a temporal holdout evaluation")
        candidate = ShipmentDelayModel()
        candidate.fit(
            train,
            model_version="shipment-lightgbm-evaluation",
            development_model=development_data,
            minimum_samples=2,
        )
        predicted = np.asarray(
            [
                candidate.predict(item.features).predicted_delay_hours
                for item in test
            ],
            dtype=np.float64,
        )
        actual = np.asarray(
            [item.actual_delay_hours for item in test], dtype=np.float64
        )
        baseline = np.full(len(test), np.median([item.actual_delay_hours for item in train]))
        return ModelEvaluation(
            model_name="shipment-delay-lightgbm",
            training_sample_count=len(train),
            evaluation_sample_count=len(test),
            mean_absolute_error=float(mean_absolute_error(actual, predicted)),
            root_mean_squared_error=float(root_mean_squared_error(actual, predicted)),
            median_baseline_mae=float(mean_absolute_error(actual, baseline)),
            development_data=development_data,
        )

    def save(self, artifact_path: str | Path) -> None:
        booster, encoder = self._require_ready()
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = path.with_suffix(path.suffix + ".json")
        with NamedTemporaryFile(
            mode="w", suffix=".txt", dir=path.parent, delete=False, encoding="utf-8"
        ) as temporary:
            temporary_path = Path(temporary.name)
        metadata_temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        metadata = {
            "model_version": self.model_version,
            "development_model": self.development_model,
            "training_sample_count": self.training_sample_count,
            "feature_names": list(encoder.feature_names),
            "medians": encoder.medians,
        }
        try:
            booster.save_model(str(temporary_path))
            metadata_temporary.write_text(
                json.dumps(metadata, sort_keys=True), encoding="utf-8"
            )
            os.replace(temporary_path, path)
            os.replace(metadata_temporary, metadata_path)
        finally:
            temporary_path.unlink(missing_ok=True)
            metadata_temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, artifact_path: str | Path) -> ShipmentDelayModel:
        path = Path(artifact_path)
        metadata_path = path.with_suffix(path.suffix + ".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        booster = lgb.Booster(model_file=str(path))
        return cls(
            booster=booster,
            encoder=NumericFeatureEncoder(
                feature_names=metadata["feature_names"],
                medians=metadata["medians"],
            ),
            model_version=metadata["model_version"],
            development_model=metadata["development_model"],
            training_sample_count=metadata["training_sample_count"],
        )

    def _require_ready(self) -> tuple[lgb.Booster, NumericFeatureEncoder]:
        if not self.ready or self.booster is None or self.encoder is None:
            raise RuntimeError("shipment delay model is not trained or loaded")
        return self.booster, self.encoder
