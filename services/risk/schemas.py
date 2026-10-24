from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskCategory(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SupplierFeatureVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str = Field(min_length=1)
    as_of: datetime
    telemetry_available: bool
    telemetry_count_24h: int = Field(ge=0)
    temperature_mean_c: float | None = None
    temperature_max_c: float | None = None
    temperature_alert_rate_24h: float | None = Field(default=None, ge=0, le=1)
    humidity_alert_rate_24h: float | None = Field(default=None, ge=0, le=1)
    telemetry_age_hours: float | None = Field(default=None, ge=0)
    disruptions_30d: int = Field(ge=0)
    active_disruptions: int = Field(ge=0)
    supplier_active: bool | None = None
    supplier_suspended: bool | None = None
    dependency_exposure_available: bool
    supplier_dependency_count: int | None = Field(default=None, ge=0)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("as_of must include a UTC offset")
        return value

    def model_features(self) -> dict[str, float | None]:
        return {
            "telemetry_available": float(self.telemetry_available),
            "telemetry_count_24h": float(self.telemetry_count_24h),
            "temperature_mean_c": self.temperature_mean_c,
            "temperature_max_c": self.temperature_max_c,
            "temperature_alert_rate_24h": self.temperature_alert_rate_24h,
            "humidity_alert_rate_24h": self.humidity_alert_rate_24h,
            "telemetry_age_hours": self.telemetry_age_hours,
            "disruptions_30d": float(self.disruptions_30d),
            "active_disruptions": float(self.active_disruptions),
            "supplier_active": (
                float(self.supplier_active) if self.supplier_active is not None else None
            ),
            "supplier_suspended": (
                float(self.supplier_suspended) if self.supplier_suspended is not None else None
            ),
            "dependency_exposure_available": float(
                self.dependency_exposure_available
            ),
            "supplier_dependency_count": (
                float(self.supplier_dependency_count)
                if self.supplier_dependency_count is not None
                else None
            ),
        }


class SupplierRiskPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str
    category: RiskCategory
    probabilities: dict[RiskCategory, float]
    model_version: str
    predicted_at: datetime
    development_model: bool

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(
        cls, value: dict[RiskCategory, float]
    ) -> dict[RiskCategory, float]:
        if set(value) != set(RiskCategory):
            raise ValueError("probabilities must include every risk category")
        if any(not math.isfinite(item) or not 0 <= item <= 1 for item in value.values()):
            raise ValueError("risk probabilities must be finite values between 0 and 1")
        if not math.isclose(sum(value.values()), 1.0, abs_tol=1e-6):
            raise ValueError("risk probabilities must sum to 1")
        return value


class ShipmentFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(min_length=1)
    as_of: datetime
    planned_transit_hours: float = Field(gt=0)
    historical_route_delay_hours: float | None = Field(default=None, ge=0)
    supplier_delay_rate_90d: float | None = Field(default=None, ge=0, le=1)
    route_disruption_count_30d: int | None = Field(default=None, ge=0)
    telemetry_alert_rate: float | None = Field(default=None, ge=0, le=1)

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("as_of must include a UTC offset")
        return value

    def model_features(self) -> dict[str, float | None]:
        return {
            "planned_transit_hours": self.planned_transit_hours,
            "historical_route_delay_hours": self.historical_route_delay_hours,
            "supplier_delay_rate_90d": self.supplier_delay_rate_90d,
            "route_disruption_count_30d": (
                float(self.route_disruption_count_30d)
                if self.route_disruption_count_30d is not None
                else None
            ),
            "telemetry_alert_rate": self.telemetry_alert_rate,
        }


class ShipmentDelayPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    predicted_delay_hours: float = Field(ge=0)
    model_version: str
    predicted_at: datetime
    development_model: bool


class ShipmentDelayTrainingExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: ShipmentFeatures
    actual_delay_hours: float = Field(ge=0)
    labeled_at: datetime

    @field_validator("labeled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("labeled_at must include a UTC offset")
        return value

    @field_validator("labeled_at")
    @classmethod
    def label_must_follow_forecast(cls, value: datetime, info) -> datetime:
        feature_time = info.data.get("features")
        if feature_time is not None and value < feature_time.as_of:
            raise ValueError("labeled_at must not precede the feature as_of time")
        return value


class ModelReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    ready: bool
    sample_count: int = Field(ge=0)
    label_source: str | None = None
    reason: str | None = None
    development_model: bool = False
    evaluation: dict[str, object] | None = None


class ModelEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    training_sample_count: int = Field(ge=1)
    evaluation_sample_count: int = Field(ge=1)
    accuracy: float | None = Field(default=None, ge=0, le=1)
    balanced_accuracy: float | None = Field(default=None, ge=0, le=1)
    macro_f1: float | None = Field(default=None, ge=0, le=1)
    mean_absolute_error: float | None = Field(default=None, ge=0)
    root_mean_squared_error: float | None = Field(default=None, ge=0)
    median_baseline_mae: float | None = Field(default=None, ge=0)
    development_data: bool


class FeatureContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_name: str
    value: float | None
    contribution: float
    imputed: bool = False


class ModelExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    model_version: str
    prediction: str | float
    explained_at: datetime
    expected_value: float
    contributions: list[FeatureContribution]
    method: str = "SHAP TreeExplainer"


class CompositeRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str
    score: float | None = Field(default=None, ge=0, le=100)
    severity: str
    scoring_version: str
    assessed_at: datetime
    coverage: float = Field(ge=0, le=1)
    components: dict[str, float | None]
    weighted_contributions: dict[str, float | None]
    missing_components: list[str]
    observed_signals: list[str]
    predicted_signals: list[str]
    calibrated_probability: bool = False
