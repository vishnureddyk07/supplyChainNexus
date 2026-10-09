"""Idempotent PostgreSQL persistence for canonical Kafka events."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class PostgresEventRepository:
    def __init__(self, pool: Any) -> None:
        self.pool = pool

    async def ensure_schema(self) -> None:
        await self.pool.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_events (
                event_id TEXT PRIMARY KEY, source TEXT NOT NULL, event_type TEXT NOT NULL,
                supplier_id TEXT, occurred_at TIMESTAMPTZ, payload JSONB NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS supplier_data (
                supplier_id TEXT PRIMARY KEY, supplier_name TEXT, contact_email TEXT,
                phone TEXT, country TEXT, status TEXT, last_event_id TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS telemetry (
                event_id TEXT PRIMARY KEY REFERENCES ingestion_events(event_id),
                supplier_id TEXT NOT NULL, temperature DOUBLE PRECISION NOT NULL,
                humidity DOUBLE PRECISION NOT NULL, recorded_at TIMESTAMPTZ NOT NULL,
                payload JSONB NOT NULL
            );
        """)

    async def persist(self, event: dict[str, Any]) -> bool:
        """Persist once; return False for a duplicate event_id."""
        payload = event.get("payload")
        if not isinstance(payload, dict) or not event.get("event_id"):
            raise ValueError("event_id and object payload are required")
        supplier_id = payload.get("supplier_id")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetchval(
                    """INSERT INTO ingestion_events
                    (event_id, source, event_type, supplier_id, occurred_at, payload, metadata)
                    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
                    ON CONFLICT (event_id) DO NOTHING RETURNING event_id""",
                    event["event_id"], event.get("source", "unknown"),
                    event.get("event_type", "unknown"), supplier_id,
                    _timestamp(event.get("occurred_at")), json.dumps(payload),
                    json.dumps(event.get("metadata", {})),
                )
                if inserted is None:
                    return False
                if event.get("source") == "supplier_erp" and supplier_id:
                    await connection.execute(
                        """INSERT INTO supplier_data
                        (supplier_id,supplier_name,contact_email,phone,country,status,last_event_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT (supplier_id) DO UPDATE SET
                        supplier_name=EXCLUDED.supplier_name, contact_email=EXCLUDED.contact_email,
                        phone=EXCLUDED.phone, country=EXCLUDED.country, status=EXCLUDED.status,
                        last_event_id=EXCLUDED.last_event_id, updated_at=now()""",
                        supplier_id, payload.get("supplier_name"), payload.get("contact_email"),
                        payload.get("phone"), payload.get("country"), payload.get("status"),
                        event["event_id"],
                    )
                if event.get("source") == "iot":
                    await connection.execute(
                        """INSERT INTO telemetry
                        (event_id,supplier_id,temperature,humidity,recorded_at,payload)
                        VALUES ($1,$2,$3,$4,$5,$6::jsonb) ON CONFLICT DO NOTHING""",
                        event["event_id"], supplier_id, payload["temperature"],
                        payload["humidity"], _timestamp(payload["timestamp"]), json.dumps(payload),
                    )
        return True

    async def close(self) -> None:
        close = getattr(self.pool, "close", None)
        if close is not None:
            await close()


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
