from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from .models import map_event
from .repository import GraphRepository

LOGGER = logging.getLogger("graph.consumer")
RAW_TOPICS = ("raw.shipping", "raw.weather", "raw.supplier_erp", "raw.iot", "raw.geopolitical")


class GraphConsumer:
    def __init__(self, repository: GraphRepository, bootstrap_servers: str, group_id: str = "graph-service", postgres_repository: Any = None) -> None:
        self.repository = repository
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.max_retries = int(os.getenv("GRAPH_MAX_RETRIES", "3"))
        self.consumer: Any = None
        self.producer: Any = None
        self._attempts: dict[tuple[str, int, int], int] = {}
        self.postgres_repository = postgres_repository

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

        self.consumer = AIOKafkaConsumer(
            *RAW_TOPICS,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=False,
            auto_offset_reset=os.getenv("GRAPH_AUTO_OFFSET_RESET", "earliest"),
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.repository.ensure_schema()
        if self.postgres_repository is not None:
            await self.postgres_repository.ensure_schema()
        await self.consumer.start()
        await self.producer.start()

    async def process(self, message: Any) -> None:
        try:
            raw_event = message.value
            if isinstance(raw_event, bytes):
                raw_event = raw_event.decode("utf-8")
            event = raw_event if isinstance(raw_event, dict) else json.loads(raw_event)
            if not isinstance(event, dict):
                raise ValueError("Kafka event must be a JSON object")
            if self.postgres_repository is not None:
                await self.postgres_repository.persist(event)
            await self.repository.upsert(map_event(event))
            await self.consumer.commit()
        except Exception as exc:
            key = (message.topic, message.partition, message.offset)
            attempts = self._attempts.get(key, 0) + 1
            if attempts < max(1, self.max_retries):
                self._attempts[key] = attempts
                LOGGER.warning("graph_event_retry", extra={"topic": message.topic, "error": str(exc), "attempt": attempts + 1})
                await asyncio.sleep(min(2 ** attempts, 10))
                raise
            await self._publish_poison(message, exc)
            await self.consumer.commit()
            self._attempts.pop(key, None)
            LOGGER.error("graph_event_poisoned", extra={"topic": message.topic, "partition": message.partition, "offset": message.offset, "error": str(exc)})

    async def _publish_poison(self, message: Any, error: Exception) -> None:
        if self.producer is None:
            return
        payload = {
            "topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
            "error": str(error),
            "event": message.value,
        }
        await self.producer.send_and_wait("raw.dlq", json.dumps(payload).encode("utf-8"))

    async def run(self, stop: asyncio.Event) -> None:
        await self.start()
        try:
            async for message in self.consumer:
                if stop.is_set():
                    break
                try:
                    await self.process(message)
                except Exception:
                    continue
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self.consumer is not None:
            await self.consumer.stop()
        if self.producer is not None:
            await self.producer.stop()
        if self.postgres_repository is not None:
            await self.postgres_repository.close()
