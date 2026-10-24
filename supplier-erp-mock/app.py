import os

from fastapi import FastAPI, HTTPException, Path
from generator import generate_supplier
from schemas import SupplierEvent
from mqtt_publisher import publish_supplier_event
from supplychain_nexus.logging_config import configure_logging

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
app = FastAPI(title="Supplier ERP Mock Service")


@app.get("/")
def home():
    return {"message": "Supplier ERP Mock Service Running"}


@app.get("/supplier-event", response_model=SupplierEvent)
def supplier_event():
    event = generate_supplier()
    try:
        publish_supplier_event(event)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return event


@app.get("/supplier-events/{count}", response_model=list[SupplierEvent])
def supplier_events(count: int = Path(ge=1, le=100)):
    events = [generate_supplier() for _ in range(count)]
    try:
        for event in events:
            publish_supplier_event(event)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return events
