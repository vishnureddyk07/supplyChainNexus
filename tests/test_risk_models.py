from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.risk.composite import CompositeRiskScorer
from services.risk.explainability import (
    explain_shipment_prediction,
    explain_supplier_prediction,
)
from services.risk.schemas import (
    RiskCategory,
    ShipmentDelayTrainingExample,
    ShipmentFeatures,
    SupplierFeatureVector,
)
from services.risk.features import SupplierFeatureRepository
from services.risk.shipment_model import ShipmentDelayModel
from services.risk.supplier_model import (
    SupplierRiskExample,
    SupplierRiskModel,
    SupplierRiskTrainingRepository,
)


def _supplier_features(index: int, risky: bool = False) -> SupplierFeatureVector:
    return SupplierFeatureVector(
        supplier_id=f"development-supplier-{index}",
        as_of=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        telemetry_available=True,
        telemetry_count_24h=20 + index,
        temperature_mean_c=50.0 if risky else 20.0,
        temperature_max_c=55.0 if risky else 25.0,
        temperature_alert_rate_24h=0.9 if risky else 0.0,
        humidity_alert_rate_24h=0.8 if risky else 0.0,
        telemetry_age_hours=1.0,
        disruptions_30d=4 if risky else 0,
        active_disruptions=1 if risky else 0,
        supplier_active=not risky,
        supplier_suspended=risky,
        dependency_exposure_available=False,
        supplier_dependency_count=None,
    )


def _shipment_example(index: int) -> ShipmentDelayTrainingExample:
    as_of = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index)
    features = ShipmentFeatures(
        shipment_id=f"development-shipment-{index}",
        as_of=as_of,
        planned_transit_hours=24 + index % 10,
        historical_route_delay_hours=float(index % 5),
        supplier_delay_rate_90d=(index % 10) / 10,
        route_disruption_count_30d=index % 4,
        telemetry_alert_rate=(index % 10) / 10,
    )
    return ShipmentDelayTrainingExample(
        features=features,
        actual_delay_hours=float(index % 10),
        labeled_at=as_of + timedelta(days=1),
    )


def test_supplier_random_forest_predicts_and_safely_roundtrips(tmp_path) -> None:
    examples = [
        SupplierRiskExample(
            features=_supplier_features(index, risky=index % 2 == 1),
            label=RiskCategory.HIGH if index % 2 else RiskCategory.LOW,
        )
        for index in range(40)
    ]
    model = SupplierRiskModel()
    model.fit(examples, development_model=True)

    prediction = model.predict(_supplier_features(41, risky=True))
    assert prediction.category == RiskCategory.HIGH
    assert prediction.development_model is True
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0)

    artifact = tmp_path / "supplier-risk.skops"
    model.save(artifact)
    loaded = SupplierRiskModel.load(artifact)
    assert loaded.predict(_supplier_features(41, risky=True)).category == prediction.category

    explanation = explain_supplier_prediction(loaded, _supplier_features(41, risky=True))
    assert explanation.method == "SHAP TreeExplainer"
    assert explanation.contributions
    assert any(item.feature_name.endswith("__missing") for item in explanation.contributions)


def test_shipment_lightgbm_trains_predicts_explains_and_roundtrips(tmp_path) -> None:
    examples = [_shipment_example(index) for index in range(40)]
    model = ShipmentDelayModel()
    model.fit(examples, development_model=True)
    prediction = model.predict(examples[-1].features)
    assert prediction.predicted_delay_hours >= 0
    assert prediction.development_model is True

    evaluation = model.evaluate_temporal(examples, development_data=True)
    assert evaluation.training_sample_count == 32
    assert evaluation.evaluation_sample_count == 8
    assert evaluation.mean_absolute_error is not None
    assert evaluation.median_baseline_mae is not None
    assert evaluation.development_data is True

    explanation = explain_shipment_prediction(model, examples[-1].features)
    assert explanation.method == "SHAP TreeExplainer"
    assert explanation.contributions

    artifact = tmp_path / "shipment-delay.txt"
    model.save(artifact)
    loaded = ShipmentDelayModel.load(artifact)
    loaded_prediction = loaded.predict(examples[-1].features)
    assert loaded_prediction.predicted_delay_hours == pytest.approx(
        prediction.predicted_delay_hours
    )


def test_composite_risk_preserves_unknown_when_signal_coverage_is_low() -> None:
    features = SupplierFeatureVector(
        supplier_id="supplier-unknown",
        as_of=datetime(2026, 1, 1, tzinfo=UTC),
        telemetry_available=False,
        telemetry_count_24h=0,
        disruptions_30d=0,
        active_disruptions=0,
        supplier_active=None,
        supplier_suspended=None,
        dependency_exposure_available=False,
        supplier_dependency_count=None,
    )
    assessment = CompositeRiskScorer().assess(features)

    assert assessment.score is None
    assert assessment.severity == "unknown"
    assert assessment.coverage == pytest.approx(0.2)
    assert assessment.calibrated_probability is False


def test_composite_risk_reports_weighted_contributions() -> None:
    features = _supplier_features(1, risky=True)
    assessment = CompositeRiskScorer().assess(features)

    assert assessment.score is not None
    assert assessment.severity == "critical"
    assert assessment.coverage == pytest.approx(0.5)
    assert sum(assessment.weighted_contributions.values()) == pytest.approx(
        assessment.score
    )


def test_shipment_label_must_follow_feature_time() -> None:
    features = ShipmentFeatures(
        shipment_id="shipment-1",
        as_of=datetime(2026, 1, 2, tzinfo=UTC),
        planned_transit_hours=10,
    )
    with pytest.raises(ValueError, match="must not precede"):
        ShipmentDelayTrainingExample(
            features=features,
            actual_delay_hours=2,
            labeled_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_training_feature_snapshot_excludes_events_at_label_timestamp() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.query = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, parameters) -> None:
            self.query = query

        def fetchone(self):
            if "telemetry_count" in self.query:
                return (0, None, None, None, None, None)
            if "count(*) FILTER" in self.query:
                return (0, 0)
            return None

    class Connection:
        def __init__(self) -> None:
            self.cursor_value = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def cursor(self):
            return self.cursor_value

    connection = Connection()
    repository = SupplierFeatureRepository(
        "postgresql://unused",
        connection_factory=lambda *args, **kwargs: connection,
    )
    features = repository.snapshot(
        "supplier-1",
        datetime(2026, 1, 2, tzinfo=UTC),
        include_as_of=False,
    )

    assert features.telemetry_count_24h == 0
    assert "occurred_at < %s" in connection.cursor_value.query
    assert "payload #>> '{supplier_data,status}'" in connection.cursor_value.query


def test_risk_training_uses_configured_labels_and_strict_past_features() -> None:
    scored_at = datetime(2026, 1, 2, tzinfo=UTC)

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, query, parameters) -> None:
            self.query = query
            self.parameters = parameters

        def fetchall(self):
            return [("supplier-1", "high", scored_at)]

    class Connection:
        def __init__(self) -> None:
            self.cursor_value = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def cursor(self):
            return self.cursor_value

    class Features:
        def __init__(self) -> None:
            self.calls = []

        def snapshot(self, supplier_id, timestamp, *, include_as_of):
            self.calls.append((supplier_id, timestamp, include_as_of))
            return _supplier_features(1)

    connection = Connection()
    feature_repository = Features()
    repository = SupplierRiskTrainingRepository(
        "postgresql://unused",
        feature_repository=feature_repository,
        label_sources=("audited",),
        connection_factory=lambda *args, **kwargs: connection,
    )

    examples = repository.load_examples(as_of=scored_at)

    assert examples[0].label == RiskCategory.HIGH
    assert connection.cursor_value.parameters == (scored_at, ["audited"])
    assert "scores.score_source = ANY(%s)" in connection.cursor_value.query
    assert feature_repository.calls == [("supplier-1", scored_at, False)]
