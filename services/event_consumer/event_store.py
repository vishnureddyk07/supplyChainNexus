from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from supplychain_nexus.contracts import SupplyChainEvent

ConnectionFactory = Callable[..., Any]


class EventStore:
    def __init__(
        self,
        dsn: str,
        connection_factory: ConnectionFactory = psycopg.connect,
    ) -> None:
        self._dsn = dsn
        self._connection_factory = connection_factory

    def persist(self, event: SupplyChainEvent) -> bool:
        """Persist once; return False when this event ID was already recorded."""
        payload = event.model_dump(mode="json")
        with self._connection_factory(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO supply_chain_events (
                        event_id, schema_version, event_type, source_system,
                        supplier_external_id, occurred_at, payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING event_id
                    """,
                    (
                        str(event.event_id),
                        event.schema_version,
                        event.event_type,
                        event.source_system,
                        event.supplier_id,
                        event.timestamp,
                        Jsonb(payload),
                    ),
                )
                inserted = cursor.fetchone() is not None
                if inserted and event.supplier_data is not None:
                    self._upsert_supplier(cursor, event)
        return inserted

    def unprojected_graph_events(self, batch_size: int = 500) -> Iterator[SupplyChainEvent]:
        if not 1 <= batch_size <= 5000:
            raise ValueError("batch_size must be between 1 and 5000")
        last_event_id: UUID | None = None
        last_occurred_at = None
        while True:
            with self._connection_factory(self._dsn, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT e.event_id, e.occurred_at, e.payload
                        FROM supply_chain_events AS e
                        LEFT JOIN graph_projection_state AS g
                            ON g.event_id = e.event_id
                        WHERE g.event_id IS NULL
                          AND (
                              %s::timestamptz IS NULL
                              OR (e.occurred_at, e.event_id) >
                                 (%s::timestamptz, %s::uuid)
                          )
                        ORDER BY e.occurred_at, e.event_id
                        LIMIT %s
                        """,
                        (
                            last_occurred_at,
                            last_occurred_at,
                            str(last_event_id) if last_event_id else None,
                            batch_size,
                        ),
                    )
                    rows = cursor.fetchall()
            if not rows:
                return
            for event_id, occurred_at, payload in rows:
                last_event_id = event_id
                last_occurred_at = occurred_at
                yield SupplyChainEvent.model_validate(payload)

    def mark_graph_projected(self, event_id: UUID) -> None:
        with self._connection_factory(self._dsn, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO graph_projection_state (event_id, projected_at)
                    VALUES (%s, NOW())
                    ON CONFLICT (event_id) DO UPDATE
                    SET projected_at = EXCLUDED.projected_at
                    """,
                    (str(event_id),),
                )

    @staticmethod
    def _upsert_supplier(cursor: Any, event: SupplyChainEvent) -> None:
        supplier = event.supplier_data
        if supplier is None:
            return
        domain = None
        if supplier.contact_email and "@" in supplier.contact_email:
            domain = supplier.contact_email.rsplit("@", 1)[1].lower() or None
        metadata = {
            "contact_email": supplier.contact_email,
            "phone": supplier.phone,
            "country": supplier.country,
            "status": supplier.status,
            "last_event_type": event.event_type,
        }
        cursor.execute(
            """
            INSERT INTO suppliers (external_id, name, domain, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (external_id) DO UPDATE
            SET name = EXCLUDED.name,
                domain = COALESCE(EXCLUDED.domain, suppliers.domain),
                metadata = COALESCE(suppliers.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                updated_at = NOW()
            """,
            (event.supplier_id, supplier.name, domain, Jsonb(metadata)),
        )
