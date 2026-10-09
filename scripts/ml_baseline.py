"""Reproducible, dependency-light disruption prediction baseline.

The bundled dataset is explicitly synthetic and is intended to validate the
pipeline shape until historical labelled incidents are available.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Iterable, Sequence


@dataclass(frozen=True)
class DisruptionExample:
    telemetry_anomaly_count: float
    delay_hours: float
    incident_count: float
    disrupted: int


SYNTHETIC_DATASET: tuple[DisruptionExample, ...] = (
    DisruptionExample(0, 0, 0, 0),
    DisruptionExample(1, 2, 0, 0),
    DisruptionExample(2, 6, 1, 1),
    DisruptionExample(3, 10, 1, 1),
    DisruptionExample(0, 12, 0, 0),
    DisruptionExample(4, 14, 2, 1),
    DisruptionExample(1, 18, 2, 1),
    DisruptionExample(0, 1, 2, 0),
)


def disruption_probability(
    telemetry_anomaly_count: float,
    delay_hours: float,
    incident_count: float,
) -> float:
    """Return a deterministic logistic baseline probability in [0, 1]."""
    linear_score = (
        -2.8
        + 0.65 * telemetry_anomaly_count
        + 0.09 * delay_hours
        + 0.9 * incident_count
    )
    return 1 / (1 + exp(-linear_score))


def predict(
    examples: Iterable[DisruptionExample],
    threshold: float = 0.5,
) -> list[int]:
    if not 0 < threshold < 1:
        raise ValueError("threshold must be between 0 and 1")
    return [
        int(disruption_probability(item.telemetry_anomaly_count, item.delay_hours, item.incident_count) >= threshold)
        for item in examples
    ]


def evaluate(
    examples: Sequence[DisruptionExample] = SYNTHETIC_DATASET,
    threshold: float = 0.5,
) -> dict[str, float | int | str]:
    """Evaluate accuracy, precision, recall, and F1 on synthetic data."""
    if not examples:
        raise ValueError("at least one example is required")
    actual = [item.disrupted for item in examples]
    predicted = predict(examples, threshold)
    true_positive = sum(a == p == 1 for a, p in zip(actual, predicted))
    true_negative = sum(a == p == 0 for a, p in zip(actual, predicted))
    false_positive = sum(a == 0 and p == 1 for a, p in zip(actual, predicted))
    false_negative = sum(a == 1 and p == 0 for a, p in zip(actual, predicted))
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "dataset": "synthetic",
        "samples": len(examples),
        "accuracy": (true_positive + true_negative) / len(examples),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


if __name__ == "__main__":
    print(evaluate())
