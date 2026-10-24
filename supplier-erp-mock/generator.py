from __future__ import annotations

import random
from datetime import UTC, datetime
from uuid import uuid4

from faker import Faker

from supplychain_nexus.contracts import SupplyChainEvent

fake = Faker()


def generate_supplier() -> SupplyChainEvent:
    event_type = random.choice(
        [
            "supplier.created",
            "supplier.updated",
            "supplier.deleted",
        ]
    )
    return SupplyChainEvent(
        event_id=uuid4(),
        event_type=event_type,
        timestamp=datetime.now(UTC),
        supplier_id=str(uuid4()),
        source_system="supplier_erp",
        supplier_data={
            "name": fake.company(),
            "contact_email": fake.company_email(),
            "phone": fake.phone_number(),
            "country": fake.country(),
            "status": random.choice(["ACTIVE", "INACTIVE", "SUSPENDED"]),
        },
        traceability={"simulated": True},
    )
