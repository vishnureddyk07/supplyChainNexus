from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from services.risk.schemas import (
    ShipmentDelayTrainingExample,
    ShipmentFeatures,
)

ConnectionFactory = Callable[..., Any]


class ShipmentFeatureRepository:
    """Build shipment inputs using outcomes recorded before each forecast time."""

    def __init__(
        self,
        dsn: str,
        connection_factory: ConnectionFactory = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._connection_factory = connection_factory

    def snapshot(
        self,
        shipment_id: str,
        as_of: datetime | None = None,
        *,
        include_as_of: bool = True,
    ) -> ShipmentFeatures:
        with self._connection_factory(
            self._dsn, connect_timeout=5, row_factory=dict_row
        ) as connection:
            shipment = connection.execute(
                """
                SELECT shipment_id, supplier_external_id, origin_name,
                       destination_name, planned_departure, planned_arrival
                FROM shipments
                WHERE shipment_id = %s
                """,
                (shipment_id,),
            ).fetchone()
            if shipment is None:
                raise LookupError(f"shipment {shipment_id!r} does not exist")
            instant = as_of or shipment["planned_departure"]
            if instant.utcoffset() is None:
                raise ValueError("as_of must include a UTC offset")
            inclusive_operator = "<=" if include_as_of else "<"
            planned_hours = (
                shipment["planned_arrival"] - shipment["planned_departure"]
            ).total_seconds() / 3600
            route = connection.execute(
                f"""
                SELECT avg(GREATEST(EXTRACT(
                           EPOCH FROM (actual_arrival - planned_arrival)
                       ) / 3600.0, 0)) AS mean_delay
                FROM shipments
                WHERE origin_name = %s AND destination_name = %s
                  AND actual_arrival IS NOT NULL
                  AND actual_arrival {inclusive_operator} %s
                """,
                (
                    shipment["origin_name"],
                    shipment["destination_name"],
                    instant,
                ),
            ).fetchone()
            supplier_history = connection.execute(
                f"""
                SELECT count(*) AS count,
                       avg(CASE WHEN actual_arrival > planned_arrival
                           THEN 1.0 ELSE 0.0 END) AS delay_rate
                FROM shipments
                WHERE supplier_external_id = %s
                  AND actual_arrival IS NOT NULL
                  AND actual_arrival >= %s
                  AND actual_arrival {inclusive_operator} %s
                """,
                (
                    shipment["supplier_external_id"],
                    instant - timedelta(days=90),
                    instant,
                ),
            ).fetchone()
            disruptions = connection.execute(
                f"""
                SELECT count(*) AS count
                FROM disruption_log AS disruption
                JOIN suppliers AS supplier ON supplier.id = disruption.supplier_id
                WHERE supplier.external_id = %s
                  AND disruption.detected_at >= %s
                  AND disruption.detected_at {inclusive_operator} %s
                """,
                (
                    shipment["supplier_external_id"],
                    instant - timedelta(days=30),
                    instant,
                ),
            ).fetchone()["count"]
            telemetry = connection.execute(
                f"""
                SELECT count(*) AS total,
                       count(*) FILTER (
                           WHERE (payload->'sensor_measurements'->>'temperature')
                               ::double precision > 45
                              OR (payload->'sensor_measurements'->>'humidity')
                               ::double precision > 80
                       ) AS alerted
                FROM supply_chain_events
                WHERE supplier_external_id = %s
                  AND source_system = 'sensor_simulator'
                  AND event_type = 'sensor.telemetry'
                  AND occurred_at >= %s
                  AND occurred_at {inclusive_operator} %s
                """,
                (shipment["supplier_external_id"], instant - timedelta(hours=24), instant),
            ).fetchone()

        return ShipmentFeatures(
            shipment_id=shipment["shipment_id"],
            as_of=instant,
            planned_transit_hours=planned_hours,
            historical_route_delay_hours=route["mean_delay"],
            supplier_delay_rate_90d=(
                supplier_history["delay_rate"]
                if supplier_history["count"]
                else None
            ),
            route_disruption_count_30d=disruptions,
            telemetry_alert_rate=(
                telemetry["alerted"] / telemetry["total"]
                if telemetry["total"]
                else None
            ),
        )


class ShipmentTrainingRepository:
    def __init__(
        self,
        dsn: str,
        feature_repository: ShipmentFeatureRepository | None = None,
        connection_factory: ConnectionFactory = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._features = feature_repository or ShipmentFeatureRepository(dsn)
        self._connection_factory = connection_factory

    def load_examples(
        self,
        *,
        development_data: bool = False,
    ) -> list[ShipmentDelayTrainingExample]:
        with self._connection_factory(
            self._dsn, connect_timeout=5, row_factory=dict_row
        ) as connection:
            rows = connection.execute(
                """
                SELECT shipment_id, actual_arrival, planned_arrival,
                       planned_departure
                FROM shipments
                WHERE actual_arrival IS NOT NULL
                  AND (NOT simulated OR %s)
                ORDER BY actual_arrival, shipment_id
                """,
                (development_data,),
            ).fetchall()
        examples = []
        for row in rows:
            features = self._features.snapshot(
                row["shipment_id"],
                as_of=row["planned_departure"],
                include_as_of=False,
            )
            delay = max(
                0.0,
                (row["actual_arrival"] - row["planned_arrival"]).total_seconds()
                / 3600,
            )
            examples.append(
                ShipmentDelayTrainingExample(
                    features=features,
                    actual_delay_hours=delay,
                    labeled_at=row["actual_arrival"],
                )
            )
        return examples
