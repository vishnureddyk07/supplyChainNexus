from pydantic import BaseModel


class SupplierEvent(BaseModel):
	supplier_id: str
	supplier_name: str
	contact_email: str
	phone: str
	country: str
	status: str
	event_type: str
	timestamp: str
