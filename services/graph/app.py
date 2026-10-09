from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI
from neo4j import AsyncGraphDatabase

from .consumer import GraphConsumer
from .repository import GraphRepository

app = FastAPI(title="Supply Chain Graph Service")
consumer_task: asyncio.Task[None] | None = None
consumer: GraphConsumer | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok" if consumer is not None else "starting"}


async def run() -> None:
    global consumer, consumer_task
    driver = AsyncGraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password")),
    )
    consumer = GraphConsumer(GraphRepository(driver), os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"))
    stop = asyncio.Event()
    consumer_task = asyncio.create_task(consumer.run(stop))
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_config=None))
    try:
        await server.serve()
    finally:
        stop.set()
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(run())
