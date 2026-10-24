from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg

from services.graph.service import SupplyChainGraph
from services.risk.schemas import SupplierFeatureVector

ConnectionFactory = Callable[..., Any]


class SupplierFeatureRepository:
    def __init__(
        self,
        dsn: str,
        graph: SupplyChainGraph | None = None,
        connection_factory: ConnectionFactory = psycopg.connect,
        temperature_alert_c: float = 45.0,
        humidity_alert_percent: float = 80.0,
    ) -> None:
        if not 0 <= humidity_alert_percent <= 100:
            raise ValueError("humidity_alert_percent must be between 0 and 100")
        self._dsn = dsn
        self._graph = graph
        self._connection_factory = connection_factory
        self._temperature_alert_c = temperature_alert_c
        self._humidity_alert_percent = humidity_alert_percent

    def snapshot(
        self,
        supplier_id: str,
        as_of: datetime | None = None,
        *,
        include_as_of: bool = True,
    ) -> SupplierFeatureVector:
        instant = as_of or datetime.now(UTC)
        if instant.utcoffset() is None:
            raise ValueError("as_of must include a UTC offset")
        since = instant - timedelta(hours=24)
        disruptions_since = instant - timedelta(days=30)
        comparison = "<=" if include_as_of else "<"

        with self._connection_factory(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        count(*) AS telemetry_count,
                        avg((payload->'sensor_measurements'->>'temperature')::double precision),
                        max((payload->'sensor_measurements'->>'temperature')::double precision),
                        avg(CASE
                            WHEN (payload->'sensor_measurements'->>'temperature')::double precision > %s
                            THEN 1.0 ELSE 0.0 END),
                        avg(CASE
                            WHEN (payload->'sensor_measurements'->>'humidity')::double precision > %s
                            THEN 1.0 ELSE 0.0 END),
                        max(occurred_at)
                    FROM supply_chain_events
                    WHERE supplier_external_id = %s
                      AND source_system = 'sensor_simulator'
                      AND event_type = 'sensor.telemetry'
                      AND occurred_at > %s
                      AND occurred_at {comparison} %s
                    """,
                    (
                        self._temperature_alert_c,
                        self._humidity_alert_percent,
                        supplier_id,
                        since,
                        instant,
                    ),
                )
                (
                    telemetry_count,
                    temperature_mean,
                    temperature_max,
                    temperature_alert_rate,
                    humidity_alert_rate,
                    latest_telemetry_at,
                ) = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT count(*) FILTER (
                               WHERE detected_at >= %s
                                 AND detected_at {comparison} %s
                           ),
                           count(*) FILTER (
                               WHERE detected_at {comparison} %s
                                 AND (resolved_at IS NULL OR resolved_at > %s)
                           )
                    FROM disruption_log AS d
                    JOIN suppliers AS s ON s.id = d.supplier_id
                    WHERE s.external_id = %s
                    """,
                    (
                        disruptions_since,
                        instant,
                        instant,
                        instant,
                        supplier_id,
                    ),
                )
                disruptions_30d, active_disruptions = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT event_type, payload #>> '{{supplier_data,status}}'
                    FROM supply_chain_events
                    WHERE supplier_external_id = %s
                      AND source_system = 'supplier_erp'
                      AND occurred_at {comparison} %s
                    ORDER BY occurred_at DESC, event_id DESC
                    LIMIT 1
                    """,
                    (supplier_id, instant),
                )
                status_record = cursor.fetchone()

        deleted = bool(status_record and status_record[0] == "supplier.deleted")
        status = status_record[1] if status_record else None
        dependency_count = (
            self._graph.get_supplier_dependency_count(supplier_id)
            if self._graph is not None
            else None
        )
        dependency_available = dependency_count is not None
        return SupplierFeatureVector(
            supplier_id=supplier_id,
            as_of=instant,
            telemetry_available=telemetry_count > 0,
            telemetry_count_24h=telemetry_count,
            temperature_mean_c=temperature_mean,
            temperature_max_c=temperature_max,
            temperature_alert_rate_24h=temperature_alert_rate,
            humidity_alert_rate_24h=humidity_alert_rate,
            telemetry_age_hours=(
                max(0.0, (instant - latest_telemetry_at).total_seconds() / 3600)
                if latest_telemetry_at
                else None
            ),
            disruptions_30d=disruptions_30d,
            active_disruptions=active_disruptions,
            supplier_active=(False if deleted else status == "ACTIVE") if status else deleted,
            supplier_suspended=status == "SUSPENDED" if status else None,
            dependency_exposure_available=dependency_available,
            supplier_dependency_count=dependency_count,
        )
