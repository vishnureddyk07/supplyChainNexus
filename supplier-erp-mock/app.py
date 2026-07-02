from fastapi import FastAPI
from generator import generate_supplier
from schemas import CanonicalEvent

app = FastAPI(title="Supplier ERP Mock Service")


@app.get("/")
def home():
    return {"message": "Supplier ERP Mock Service Running"}


@app.get("/supplier-event", response_model=CanonicalEvent)
def supplier_event():
    return generate_supplier()


@app.get("/supplier-events/{count}", response_model=list[CanonicalEvent])
def supplier_events(count: int):
    return [generate_supplier() for _ in range(count)]