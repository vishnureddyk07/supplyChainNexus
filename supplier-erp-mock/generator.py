from faker import Faker
from uuid import uuid4
from datetime import datetime, timezone
import random

fake = Faker()


def generate_supplier():
    status = random.choice([
        "ACTIVE",
        "INACTIVE",
        "SUSPENDED",
    ])
    event_type = random.choice([
        "supplier.created",
        "supplier.updated",
        "supplier.deleted",
    ])
    event_action = {
        "supplier.created": "CREATED",
        "supplier.updated": "UPDATED",
        "supplier.deleted": "DELETED",
    }[event_type]
    supplier_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "event_version": "1.0",
        "schema_version": "1.0",
        "occurred_at": timestamp,
        "ingested_at": None,
        "source": {
            "system": "supplier_erp",
            "service": "supplier-erp-mock",
            "environment": "local"
        },
        "entity": {
            "type": "supplier",
            "id": supplier_id,
        },
        "tenant_id": "global",
        "correlation_id": str(uuid4()),
        "causation_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "payload": {
            "supplier_id": supplier_id,
            "supplier_name": fake.company(),
            "contact_email": fake.company_email(),
            "phone": fake.phone_number(),
            "country": fake.country(),
            "status": status,
            "event_action": event_action,
        },
        "metadata": {
            "content_type": "application/json",
            "region": fake.country_code(),
        },
    }