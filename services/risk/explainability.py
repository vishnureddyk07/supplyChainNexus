from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import shap

from services.risk.schemas import (
    FeatureContribution,
    ModelExplanation,
    ShipmentFeatures,
    SupplierFeatureVector,
)
from services.risk.shipment_model import ShipmentDelayModel
from services.risk.supplier_model import SupplierRiskModel


def explain_supplier_prediction(
    model: SupplierRiskModel,
    features: SupplierFeatureVector,
) -> ModelExplanation:
    classifier, encoder = model._require_ready()
    matrix = encoder.transform([features.model_features()])
    predicted_category = model.predict(features).category.value
    class_index = list(classifier.classes_).index(predicted_category)
    explainer = shap.TreeExplainer(classifier)
    values = explainer.shap_values(matrix, check_additivity=False)
    contributions = _select_shap_row(values, class_index, matrix.shape[1])
    expected = _select_expected_value(explainer.expected_value, class_index)
    return _make_explanation(
        "supplier-risk-random-forest",
        model.model_version,
        predicted_category,
        expected,
        contributions,
        encoder.encoded_feature_names,
        features.model_features(),
    )


def explain_shipment_prediction(
    model: ShipmentDelayModel,
    features: ShipmentFeatures,
) -> ModelExplanation:
    booster, encoder = model._require_ready()
    matrix = encoder.transform([features.model_features()])
    prediction = float(booster.predict(matrix)[0])
    explainer = shap.TreeExplainer(booster)
    values = explainer.shap_values(matrix, check_additivity=False)
    contributions = _select_shap_row(values, 0, matrix.shape[1])
    expected = _select_expected_value(explainer.expected_value, 0)
    return _make_explanation(
        "shipment-delay-lightgbm",
        model.model_version,
        prediction,
        expected,
        contributions,
        encoder.encoded_feature_names,
        features.model_features(),
    )


def _select_shap_row(values: Any, class_index: int, feature_count: int) -> np.ndarray:
    if isinstance(values, list):
        matrix = np.asarray(values[class_index])
        return matrix[0] if matrix.ndim == 2 else matrix
    array = np.asarray(values)
    if array.ndim == 3:
        if array.shape[0] == 1 and array.shape[1] == feature_count:
            return array[0, :, class_index]
        if array.shape[1] == 1 and array.shape[2] == feature_count:
            return array[class_index, 0, :]
    if array.ndim == 2 and array.shape[1] == feature_count:
        return array[0]
    raise ValueError(f"unexpected SHAP output shape: {array.shape}")


def _select_expected_value(values: Any, class_index: int) -> float:
    array = np.asarray(values)
    if array.ndim == 0:
        return float(array)
    return float(array.reshape(-1)[class_index])


def _make_explanation(
    model_name: str,
    model_version: str,
    prediction: str | float,
    expected_value: float,
    shap_values: np.ndarray,
    encoded_names: tuple[str, ...],
    original_features: dict[str, float | None],
) -> ModelExplanation:
    feature_count = len(original_features)
    items = []
    for index, name in enumerate(encoded_names):
        if index < feature_count:
            value = original_features[name]
            items.append(
                FeatureContribution(
                    feature_name=name,
                    value=value,
                    contribution=float(shap_values[index]),
                    imputed=value is None,
                )
            )
        else:
            base_name = name.removesuffix("__missing")
            value = float(original_features[base_name] is None)
            items.append(
                FeatureContribution(
                    feature_name=name,
                    value=value,
                    contribution=float(shap_values[index]),
                )
            )
    return ModelExplanation(
        model_name=model_name,
        model_version=model_version,
        prediction=prediction,
        explained_at=datetime.now(UTC),
        expected_value=expected_value,
        contributions=items,
    )
