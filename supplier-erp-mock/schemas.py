from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SupplierEvent(BaseModel):
	supplier_id: str
	supplier_name: str = Field(min_length=1)
	contact_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
	phone: str = Field(min_length=1)
	country: str = Field(min_length=1)
	status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
	event_type: Literal["SUPPLIER_CREATED", "SUPPLIER_UPDATED", "SUPPLIER_DELETED"]
	timestamp: datetime
