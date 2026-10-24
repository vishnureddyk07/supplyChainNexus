from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray


class NumericFeatureEncoder:
    """Median-impute numeric inputs while retaining explicit missing-value flags."""

    def __init__(
        self,
        feature_names: Sequence[str] | None = None,
        medians: Mapping[str, float] | None = None,
    ) -> None:
        self.feature_names = tuple(feature_names or ())
        self.medians = dict(medians or {})

    def fit(self, rows: Sequence[Mapping[str, float | None]]) -> None:
        if not rows:
            raise ValueError("at least one feature row is required")
        names = tuple(rows[0])
        if any(tuple(row) != names for row in rows):
            raise ValueError("all feature rows must have the same ordered fields")
        self.feature_names = names
        self.medians = {}
        for name in names:
            values = sorted(
                value
                for row in rows
                if (value := _finite_value(row[name])) is not None
            )
            if not values:
                self.medians[name] = 0.0
                continue
            middle = len(values) // 2
            self.medians[name] = (
                values[middle]
                if len(values) % 2
                else (values[middle - 1] + values[middle]) / 2
            )

    @property
    def encoded_feature_names(self) -> tuple[str, ...]:
        return self.feature_names + tuple(
            f"{name}__missing" for name in self.feature_names
        )

    def transform(
        self, rows: Sequence[Mapping[str, float | None]]
    ) -> NDArray[np.float64]:
        if not self.feature_names or set(self.medians) != set(self.feature_names):
            raise RuntimeError("feature encoder has not been fitted")
        encoded: list[list[float]] = []
        for row in rows:
            if set(row) != set(self.feature_names):
                raise ValueError("feature row does not match the fitted schema")
            values = [_finite_value(row[name]) for name in self.feature_names]
            encoded.append(
                [
                    self.medians[name] if value is None else value
                    for name, value in zip(self.feature_names, values, strict=True)
                ]
                + [float(value is None) for value in values]
            )
        return np.asarray(encoded, dtype=np.float64)


def _finite_value(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None
