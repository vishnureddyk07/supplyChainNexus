from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import psycopg
import skops.io as skops_io
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

from services.risk.feature_encoding import NumericFeatureEncoder
from services.risk.features import SupplierFeatureRepository
from services.risk.schemas import (
    ModelEvaluation,
    ModelReadiness,
    RiskCategory,
    SupplierFeatureVector,
    SupplierRiskPrediction,
)


@dataclass(frozen=True)
class SupplierRiskExample:
    features: SupplierFeatureVector
    label: RiskCategory


class SupplierRiskTrainingRepository:
    """Build leakage-aware features from explicitly trusted historical labels."""

    def __init__(
        self,
        dsn: str,
        feature_repository: SupplierFeatureRepository | None = None,
        label_sources: Sequence[str] = ("manual", "audited"),
        connection_factory: Any = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._features = feature_repository or SupplierFeatureRepository(dsn)
        self._label_sources = tuple(source.strip() for source in label_sources if source.strip())
        self._connection_factory = connection_factory

    def readiness(
        self,
        as_of: datetime | None = None,
        *,
        examples: Sequence[SupplierRiskExample] | None = None,
    ) -> ModelReadiness:
        examples = list(examples) if examples is not None else self.load_examples(as_of=as_of)
        labels = {example.label for example in examples}
        ready = len(examples) >= 30 and len(labels) >= 2
        if ready:
            reason = None
        elif not examples:
            reason = "No trusted historical supplier risk labels are available."
        elif len(labels) < 2:
            reason = "At least two distinct risk categories are required for training."
        else:
            reason = "At least 30 trusted labeled supplier snapshots are required."
        return ModelReadiness(
            model_name="supplier-risk-random-forest",
            ready=ready,
            sample_count=len(examples),
            label_source=", ".join(self._label_sources) or None,
            reason=reason,
        )

    def load_examples(self, as_of: datetime | None = None) -> list[SupplierRiskExample]:
        if not self._label_sources:
            return []
        cutoff = as_of or datetime.now(UTC)
        if cutoff.utcoffset() is None:
            raise ValueError("as_of must include a UTC offset")
        with self._connection_factory(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.external_id, scores.risk_category, scores.scored_at
                    FROM supplier_risk_scores AS scores
                    JOIN suppliers AS s ON s.id = scores.supplier_id
                    WHERE scores.scored_at <= %s
                      AND scores.score_source = ANY(%s)
                    ORDER BY scores.scored_at, scores.id
                    """,
                    (cutoff, list(self._label_sources)),
                )
                records = cursor.fetchall()

        examples = []
        for supplier_id, category, scored_at in records:
            examples.append(
                SupplierRiskExample(
                    features=self._features.snapshot(
                        supplier_id,
                        scored_at,
                        include_as_of=False,
                    ),
                    label=RiskCategory(category),
                )
            )
        return examples


class SupplierRiskModel:
    """Random Forest classifier with safe skops persistence and missingness features."""

    def __init__(
        self,
        classifier: RandomForestClassifier | None = None,
        encoder: NumericFeatureEncoder | None = None,
        model_version: str = "supplier-rf-v1",
        development_model: bool = False,
        training_sample_count: int = 0,
    ) -> None:
        self.classifier = classifier
        self.encoder = encoder
        self.model_version = model_version
        self.development_model = development_model
        self.training_sample_count = training_sample_count

    @property
    def ready(self) -> bool:
        return self.classifier is not None and self.encoder is not None

    def fit(
        self,
        examples: Sequence[SupplierRiskExample],
        *,
        model_version: str = "supplier-rf-v1",
        development_model: bool = False,
        minimum_samples: int = 30,
    ) -> None:
        if len(examples) < minimum_samples:
            raise ValueError(
                f"at least {minimum_samples} labeled examples are required"
            )
        labels = [example.label.value for example in examples]
        if len(set(labels)) < 2:
            raise ValueError("at least two risk categories are required for training")

        rows = [example.features.model_features() for example in examples]
        encoder = NumericFeatureEncoder()
        encoder.fit(rows)
        matrix = encoder.transform(rows)
        classifier = RandomForestClassifier(
            n_estimators=300,
            class_weight="balanced_subsample",
            max_features="sqrt",
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,
        )
        classifier.fit(matrix, labels)
        self.classifier = classifier
        self.encoder = encoder
        self.model_version = model_version
        self.development_model = development_model
        self.training_sample_count = len(examples)

    def predict(self, features: SupplierFeatureVector) -> SupplierRiskPrediction:
        classifier, encoder = self._require_ready()
        matrix = encoder.transform([features.model_features()])
        probabilities = classifier.predict_proba(matrix)[0]
        probability_map = {category: 0.0 for category in RiskCategory}
        for label, probability in zip(classifier.classes_, probabilities, strict=True):
            probability_map[RiskCategory(label)] = float(probability)
        category = max(probability_map, key=probability_map.__getitem__)
        return SupplierRiskPrediction(
            supplier_id=features.supplier_id,
            category=category,
            probabilities=probability_map,
            model_version=self.model_version,
            predicted_at=datetime.now(UTC),
            development_model=self.development_model,
        )

    def evaluate_temporal(
        self,
        examples: Sequence[SupplierRiskExample],
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
        if len({item.label for item in train}) < 2:
            raise ValueError("temporal training partition must contain two categories")
        candidate = SupplierRiskModel()
        candidate.fit(
            train,
            model_version="supplier-rf-evaluation",
            development_model=development_data,
            minimum_samples=2,
        )
        predictions = [
            candidate.predict(item.features).category.value for item in test
        ]
        targets = [item.label.value for item in test]
        return ModelEvaluation(
            model_name="supplier-risk-random-forest",
            training_sample_count=len(train),
            evaluation_sample_count=len(test),
            accuracy=float(accuracy_score(targets, predictions)),
            balanced_accuracy=float(
                balanced_accuracy_score(targets, predictions)
            ),
            macro_f1=float(f1_score(targets, predictions, average="macro", zero_division=0)),
            development_data=development_data,
        )

    def save(self, artifact_path: str | Path) -> None:
        self._require_ready()
        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "model_version": self.model_version,
            "development_model": self.development_model,
            "training_sample_count": self.training_sample_count,
            "feature_names": list(self.encoder.feature_names),
            "medians": self.encoder.medians,
        }
        with NamedTemporaryFile(
            mode="wb", suffix=".skops", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        metadata_path = path.with_suffix(path.suffix + ".json")
        metadata_temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
        try:
            skops_io.dump(self.classifier, temporary_path)
            metadata_temporary.write_text(
                json.dumps(metadata, sort_keys=True), encoding="utf-8"
            )
            os.replace(temporary_path, path)
            os.replace(metadata_temporary, metadata_path)
        finally:
            temporary_path.unlink(missing_ok=True)
            metadata_temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, artifact_path: str | Path) -> SupplierRiskModel:
        path = Path(artifact_path)
        metadata_path = path.with_suffix(path.suffix + ".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        untrusted = set(skops_io.get_untrusted_types(file=path))
        trusted_types = {"sklearn.tree._tree.Tree"}
        unexpected_types = untrusted - trusted_types
        if unexpected_types:
            raise ValueError(
                "model artifact contains untrusted types: "
                + ", ".join(sorted(unexpected_types))
            )
        classifier = skops_io.load(file=path, trusted=sorted(untrusted))
        if not isinstance(classifier, RandomForestClassifier):
            raise ValueError("artifact does not contain a RandomForestClassifier")
        return cls(
            classifier=classifier,
            encoder=NumericFeatureEncoder(
                feature_names=metadata["feature_names"],
                medians=metadata["medians"],
            ),
            model_version=metadata["model_version"],
            development_model=metadata["development_model"],
            training_sample_count=metadata["training_sample_count"],
        )

    def _require_ready(
        self,
    ) -> tuple[RandomForestClassifier, NumericFeatureEncoder]:
        if not self.ready or self.classifier is None or self.encoder is None:
            raise RuntimeError("supplier risk model is not trained or loaded")
        return self.classifier, self.encoder
