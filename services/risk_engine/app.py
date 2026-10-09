from __future__ import annotations

import os

from fastapi import FastAPI, Query
from neo4j import AsyncGraphDatabase

from .queries import GraphQueryService

app = FastAPI(title="Supply Chain Risk Engine")
queries: GraphQueryService | None = None


@app.on_event("startup")
async def startup() -> None:
    global queries
    driver = AsyncGraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password")),
    )
    queries = GraphQueryService(driver)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok" if queries else "starting"}


@app.get("/dependencies")
async def dependencies(company_id: str, max_hops: int = Query(default=5, ge=1, le=5)):
    if queries is None:
        return {"status": "starting"}
    return await queries.dependencies(company_id, max_hops)


@app.get("/blast-radius")
async def blast_radius(company_id: str):
    if queries is None:
        return {"status": "starting"}
    return await queries.cascade_count(company_id)


@app.get("/alternatives")
async def alternatives(company_id: str):
    if queries is None:
        return {"status": "starting"}
    return await queries.alternatives(company_id)
