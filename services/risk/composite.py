from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
import os

from services.risk.schemas import (
    CompositeRiskAssessment,
    RiskCategory,
    ShipmentDelayPrediction,
    SupplierFeatureVector,
    SupplierRiskPrediction,
)

_DEFAULT_WEIGHTS = {
    "supplier_model_risk": 0.4,
    "disruption_pressure": 0.2,
    "telemetry_pressure": 0.2,
    "supplier_status_risk": 0.1,
    "shipment_delay_risk": 0.1,
}


class CompositeRiskScorer:
    """Transparent weighted heuristic; scores are not calibrated probabilities."""

    def __init__(
        self,
        weights: Mapping[str, float] | None = None,
        *,
        scoring_version: str = "composite-risk-v1",
        minimum_coverage: float = 0.5,
        shipment_delay_horizon_hours: float = 24.0,
    ) -> None:
        configured = dict(weights or _DEFAULT_WEIGHTS)
        if set(configured) != set(_DEFAULT_WEIGHTS):
            raise ValueError("weights must define exactly the supported components")
        if any(not math.isfinite(value) or value < 0 for value in configured.values()):
            raise ValueError("weights must be finite and non-negative")
        if not math.isclose(sum(configured.values()), 1.0, abs_tol=1e-9):
            raise ValueError("weights must sum to 1")
        if not 0 <= minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be between 0 and 1")
        if not math.isfinite(shipment_delay_horizon_hours) or shipment_delay_horizon_hours <= 0:
            raise ValueError("shipment_delay_horizon_hours must be positive")
        self._weights = configured
        self._version = scoring_version
        self._minimum_coverage = minimum_coverage
        self._delay_horizon = shipment_delay_horizon_hours

    @classmethod
    def from_env(cls) -> CompositeRiskScorer:
        weights = os.getenv("COMPOSITE_RISK_WEIGHTS")
        return cls(
            weights=json.loads(weights) if weights else None,
            scoring_version=os.getenv(
                "COMPOSITE_RISK_VERSION", "composite-risk-v1"
            ),
            minimum_coverage=float(
                os.getenv("COMPOSITE_RISK_MINIMUM_COVERAGE", "0.5")
            ),
            shipment_delay_horizon_hours=float(
                os.getenv("SHIPMENT_DELAY_RISK_HORIZON_HOURS", "24")
            ),
        )

    def assess(
        self,
        features: SupplierFeatureVector,
        *,
        supplier_prediction: SupplierRiskPrediction | None = None,
        shipment_prediction: ShipmentDelayPrediction | None = None,
    ) -> CompositeRiskAssessment:
        telemetry_rates = [
            value
            for value in (
                features.temperature_alert_rate_24h,
                features.humidity_alert_rate_24h,
            )
            if value is not None
        ]
        status_known = (
            features.supplier_active is not None
            or features.supplier_suspended is not None
        )
        components: dict[str, float | None] = {
            "supplier_model_risk": (
                sum(
                    supplier_prediction.probabilities.get(category, 0.0)
                    for category in (
                        RiskCategory.MEDIUM,
                        RiskCategory.HIGH,
                        RiskCategory.CRITICAL,
                    )
                )
                if supplier_prediction is not None
                else None
            ),
            "disruption_pressure": min(
                1.0,
                (features.disruptions_30d + features.active_disruptions) / 5,
            ),
            "telemetry_pressure": max(telemetry_rates) if telemetry_rates else None,
            "supplier_status_risk": (
                float(
                    features.supplier_suspended is True
                    or features.supplier_active is False
                )
                if status_known
                else None
            ),
            "shipment_delay_risk": (
                min(
                    1.0,
                    shipment_prediction.predicted_delay_hours
                    / self._delay_horizon,
                )
                if shipment_prediction is not None
                else None
            ),
        }
        available = {
            name: value for name, value in components.items() if value is not None
        }
        coverage = sum(self._weights[name] for name in available)
        if coverage:
            contributions = {
                name: self._weights[name] / coverage * float(value) * 100
                for name, value in available.items()
            }
            score = sum(contributions.values())
        else:
            contributions = {}
            score = None
        if score is None or coverage < self._minimum_coverage:
            severity = "unknown"
            score = None
        elif score < 25:
            severity = RiskCategory.LOW.value
        elif score < 50:
            severity = RiskCategory.MEDIUM.value
        elif score < 75:
            severity = RiskCategory.HIGH.value
        else:
            severity = RiskCategory.CRITICAL.value
        return CompositeRiskAssessment(
            supplier_id=features.supplier_id,
            score=score,
            severity=severity,
            scoring_version=self._version,
            assessed_at=datetime.now(UTC),
            coverage=coverage,
            components=components,
            weighted_contributions=contributions,
            missing_components=[
                name for name, value in components.items() if value is None
            ],
            observed_signals=[
                name
                for name in (
                    "disruption_pressure",
                    "telemetry_pressure",
                    "supplier_status_risk",
                )
                if components[name] is not None
            ],
            predicted_signals=[
                name
                for name in ("supplier_model_risk", "shipment_delay_risk")
                if components[name] is not None
            ],
            calibrated_probability=False,
        )
