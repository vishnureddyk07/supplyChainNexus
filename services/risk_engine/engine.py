"""Deterministic, explainable supplier risk calculation.

Scoring thresholds are intentionally stable and visible in the reason output:
delay contributes up to 25 points, defects 20, financial health 20,
geopolitical conditions 15, weather 10, and telemetry anomalies 5 each
(capped at 10).  Totals map to low (0-29), medium (30-59), high (60-79),
and critical (80-100).
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import Iterable

from .models import RiskReason, RiskRequest


def detect_abnormal_telemetry(values: dict[str, float]) -> list[str]:
    """Return metric names outside a conservative 3-sigma rolling sample.

    A metric can also be supplied as ``*_zscore`` by upstream anomaly models.
    This keeps the service useful with both raw sensors and pre-processed data.
    """
    abnormal: list[str] = []
    for name, value in values.items():
        if name.endswith("_zscore") and abs(value) >= 3:
            abnormal.append(name.removesuffix("_zscore"))
            continue
        if isinstance(value, (int, float)) and abs(value) >= 100:
            abnormal.append(name)
    return abnormal


def calculate_risk(request: RiskRequest) -> tuple[float, str, list[RiskReason], list[str]]:
    reasons: list[RiskReason] = []

    def add(code: str, reason: str, points: float, severity: str = "medium") -> None:
        if points > 0:
            reasons.append(RiskReason(code=code, reason=reason, points=round(points, 2), severity=severity))

    delay = min(request.delivery_delay_days / 30 * 25, 25)
    add("delivery_delay", f"Delivery delay is {request.delivery_delay_days:g} day(s)", delay,
        "high" if delay >= 15 else "medium")
    add("defect_rate", f"Defect rate is {request.defect_rate:.1%}", request.defect_rate * 20,
        "high" if request.defect_rate >= .1 else "medium")
    add("financial_health", f"Financial health is {request.financial_health:.1%}",
        (1 - request.financial_health) * 20, "high" if request.financial_health < .4 else "medium")
    add("geopolitical_risk", f"Geopolitical risk is {request.geopolitical_risk:.1%}",
        request.geopolitical_risk * 15, "high" if request.geopolitical_risk >= .7 else "medium")
    add("weather_risk", f"Weather risk is {request.weather_risk:.1%}", request.weather_risk * 10,
        "high" if request.weather_risk >= .7 else "medium")
    abnormal = detect_abnormal_telemetry(request.telemetry)
    add("abnormal_telemetry", f"Abnormal telemetry detected for: {', '.join(abnormal)}",
        min(len(abnormal) * 5, 10), "high")
    score = round(min(100, max(0, sum(item.points for item in reasons))), 2)
    level = "low" if score < 30 else "medium" if score < 60 else "high" if score < 80 else "critical"
    return score, level, reasons, abnormal
