"""Persistence adapter with PostgreSQL support and an in-memory test fallback."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
except ImportError:  # pragma: no cover - optional for local unit tests
    psycopg = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
 supplier_id TEXT PRIMARY KEY, name TEXT, country TEXT, status TEXT NOT NULL,
 event_id TEXT UNIQUE, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS risk_history (
 id BIGSERIAL PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
 event_id TEXT, fingerprint TEXT NOT NULL UNIQUE, score NUMERIC(5,2) NOT NULL,
 level TEXT NOT NULL, reasons JSONB NOT NULL, abnormal_telemetry JSONB NOT NULL,
 calculated_at TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS risk_history_supplier_time ON risk_history(supplier_id, calculated_at DESC);
CREATE TABLE IF NOT EXISTS disruptions (
 id BIGSERIAL PRIMARY KEY, supplier_id TEXT NOT NULL, event_id TEXT,
 fingerprint TEXT NOT NULL UNIQUE, disruption_type TEXT NOT NULL, severity TEXT NOT NULL,
 message TEXT NOT NULL, starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""


class Repository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.suppliers: dict[str, dict[str, Any]] = {}
        self.risks: list[dict[str, Any]] = []
        self.disruptions: list[dict[str, Any]] = []
        self.db_available = False

    def initialize(self) -> None:
        if not self.database_url or psycopg is None:
            return
        try:
            with psycopg.connect(self.database_url) as conn:
                conn.execute(SCHEMA)
            self.db_available = True
        except Exception:
            self.db_available = False

    @staticmethod
    def _fingerprint(data: Any) -> str:
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def upsert_supplier(self, supplier: dict[str, Any]) -> dict[str, Any]:
        current = self.suppliers.setdefault(supplier["supplier_id"], {})
        current.update(supplier)
        current.setdefault("status", "active")
        if self.db_available:
            with psycopg.connect(self.database_url) as conn:
                conn.execute(
                    """INSERT INTO suppliers (supplier_id,name,country,status,event_id)
                       VALUES (%(supplier_id)s,%(name)s,%(country)s,%(status)s,%(event_id)s)
                       ON CONFLICT (supplier_id) DO UPDATE SET name=EXCLUDED.name,
                       country=EXCLUDED.country,status=EXCLUDED.status,event_id=EXCLUDED.event_id""",
                    current,
                )
        return current

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        return self.suppliers.get(supplier_id)

    def add_risk(self, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        fp = record["fingerprint"]
        for existing in self.risks:
            if existing["fingerprint"] == fp:
                return existing, True
        self.risks.append(record)
        if self.db_available:
            with psycopg.connect(self.database_url) as conn:
                result = conn.execute(
                    """INSERT INTO risk_history
                       (supplier_id,event_id,fingerprint,score,level,reasons,abnormal_telemetry,calculated_at)
                       VALUES (%(supplier_id)s,%(event_id)s,%(fingerprint)s,%(score)s,%(level)s,
                       %(reasons)s::jsonb,%(abnormal_telemetry)s::jsonb,%(calculated_at)s)
                       ON CONFLICT (fingerprint) DO NOTHING""",
                    {**record, "reasons": json.dumps(record["reasons"]),
                     "abnormal_telemetry": json.dumps(record["abnormal_telemetry"])},
                )
                if result.rowcount == 0:
                    return next(r for r in self.risks if r["fingerprint"] == fp), True
        return record, False

    def history(self, supplier_id: str) -> list[dict[str, Any]]:
        return [r for r in reversed(self.risks) if r["supplier_id"] == supplier_id]

    def add_disruption(self, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        for existing in self.disruptions:
            if existing["fingerprint"] == record["fingerprint"]:
                return existing, True
        self.disruptions.append(record)
        if self.db_available:
            with psycopg.connect(self.database_url) as conn:
                result = conn.execute(
                    """INSERT INTO disruptions
                       (supplier_id,event_id,fingerprint,disruption_type,severity,message,starts_at,ends_at)
                       VALUES (%(supplier_id)s,%(event_id)s,%(fingerprint)s,%(disruption_type)s,
                       %(severity)s,%(message)s,%(starts_at)s,%(ends_at)s)
                       ON CONFLICT (fingerprint) DO NOTHING""", record)
                if result.rowcount == 0:
                    return next(d for d in self.disruptions if d["fingerprint"] == record["fingerprint"]), True
        return record, False

    def all_disruptions(self, supplier_id: str | None = None) -> list[dict[str, Any]]:
        return [d for d in self.disruptions if supplier_id is None or d["supplier_id"] == supplier_id]

    def health(self) -> str:
        return "ok" if not self.database_url or self.db_available else "degraded"


def now() -> datetime:
    return datetime.now(timezone.utc)
