from faker import Faker
from uuid import uuid4
from datetime import datetime
import random

fake = Faker()

def generate_supplier():

    return {
        "supplier_id": str(uuid4()),
        "supplier_name": fake.company(),
        "contact_email": fake.company_email(),
        "phone": fake.phone_number(),
        "country": fake.country(),
        "status": random.choice([
            "ACTIVE",
            "INACTIVE",
            "SUSPENDED"
        ]),
        "event_type": random.choice([
            "SUPPLIER_CREATED",
            "SUPPLIER_UPDATED",
            "SUPPLIER_DELETED"
        ]),
        "timestamp": datetime.utcnow().isoformat()
    }