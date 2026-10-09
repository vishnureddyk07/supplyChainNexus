"""External source connectors. Each connector isolates source failures."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable
from typing import Any

import httpx
import paho.mqtt.client as mqtt

from .events import IngestionEvent, utc_now
from .publisher import EventPublisher

LOGGER = logging.getLogger("ingestion.connectors")


def source_log(level: int, source: str, message: str, **fields: Any) -> None:
    LOGGER.log(level, message, extra={"source": source, **fields})


class HttpConnector:
    source = "unknown"

    def __init__(self, publisher: EventPublisher, client: httpx.AsyncClient | None = None) -> None:
        self.publisher = publisher
        self.client = client or httpx.AsyncClient(timeout=20.0)
        self._owns_client = client is None
        self.max_retries = int(os.getenv("INGESTION_MAX_RETRIES", "3"))
        self.backoff_seconds = float(os.getenv("INGESTION_BACKOFF_SECONDS", "1"))

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def request_json(self, url: str, **kwargs: Any) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.get(url, **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                if attempt >= self.max_retries:
                    source_log(logging.ERROR, self.source, "source_request_failed", error=str(exc), url=url)
                    raise
                delay = self.backoff_seconds * (2**attempt)
                source_log(logging.WARNING, self.source, "source_request_retry", attempt=attempt + 1, delay=delay)
                await asyncio.sleep(delay)

    async def publish_payload(self, event_type: str, payload: dict[str, Any], **metadata: Any) -> None:
        await self.publisher.publish(
            IngestionEvent(
                source=self.source,
                event_type=event_type,
                payload=payload,
                metadata=metadata,
            )
        )


class MarineTrafficConnector(HttpConnector):
    source = "shipping"
    url = "https://services.marinetraffic.com/api/exportvessel/v:8/"

    def __init__(self, publisher: EventPublisher, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(publisher, **kwargs)
        self.api_key = api_key or os.getenv("MARINETRAFFIC_API_KEY")
        self.interval = float(os.getenv("MARINETRAFFIC_POLL_SECONDS", "300"))

    async def poll_once(self) -> int:
        if not self.api_key:
            source_log(logging.WARNING, self.source, "source_disabled", reason="MARINETRAFFIC_API_KEY is not set")
            return 0
        data = await self.request_json(f"{self.url}{self.api_key}", params={"msgtype": "positions"})
        records = data if isinstance(data, list) else data.get("data", [])
        for record in records:
            await self.publish_payload("vessel_position", record, fetched_at=utc_now())
        source_log(logging.INFO, self.source, "source_batch_published", count=len(records))
        return len(records)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                source_log(logging.ERROR, self.source, "source_cycle_failed", error=str(exc))
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass


class OpenWeatherConnector(HttpConnector):
    source = "weather"
    url = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, publisher: EventPublisher, api_key: str | None = None, locations: Iterable[dict[str, Any]] | None = None, **kwargs: Any) -> None:
        super().__init__(publisher, **kwargs)
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.locations = list(locations or self._locations_from_env())
        self.interval = float(os.getenv("OPENWEATHER_POLL_SECONDS", "600"))

    @staticmethod
    def _locations_from_env() -> list[dict[str, Any]]:
        raw = os.getenv("OPENWEATHER_LOCATIONS", "")
        locations = []
        for value in raw.split(";"):
            if value.strip():
                latitude, longitude = value.split(",", 1)
                locations.append({"lat": float(latitude), "lon": float(longitude)})
        return locations

    async def fetch_location(self, location: dict[str, Any]) -> None:
        if not self.api_key:
            source_log(logging.WARNING, self.source, "source_disabled", reason="OPENWEATHER_API_KEY is not set")
            return
        payload = await self.request_json(self.url, params={**location, "appid": self.api_key, "units": "metric"})
        await self.publish_payload("weather_observation", payload, location=location)

    async def poll_once(self) -> int:
        if not self.locations:
            source_log(logging.WARNING, self.source, "source_disabled", reason="no locations configured")
            return 0
        results = await asyncio.gather(*(self.fetch_location(location) for location in self.locations), return_exceptions=True)
        failures = [result for result in results if isinstance(result, Exception)]
        for failure in failures:
            source_log(logging.ERROR, self.source, "location_fetch_failed", error=str(failure))
        return len(self.locations) - len(failures)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                source_log(logging.ERROR, self.source, "source_cycle_failed", error=str(exc))
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass


class GdeltConnector(HttpConnector):
    source = "geopolitical"
    url = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, publisher: EventPublisher, query: str | None = None, **kwargs: Any) -> None:
        super().__init__(publisher, **kwargs)
        self.query = query or os.getenv("GDELT_QUERY", "supply chain OR shipping")
        self.interval = float(os.getenv("GDELT_POLL_SECONDS", "900"))

    async def poll_once(self) -> int:
        data = await self.request_json(self.url, params={"query": self.query, "mode": "artlist", "format": "json", "maxrecords": 250})
        articles = data.get("articles", []) if isinstance(data, dict) else []
        for article in articles:
            await self.publish_payload("geopolitical_news", article, query=self.query)
        source_log(logging.INFO, self.source, "source_batch_published", count=len(articles))
        return len(articles)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                source_log(logging.ERROR, self.source, "source_cycle_failed", error=str(exc))
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass


class SupplierErpConnector(HttpConnector):
    source = "supplier_erp"

    def __init__(self, publisher: EventPublisher, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(publisher, **kwargs)
        self.base_url = (base_url or os.getenv("SUPPLIER_ERP_URL", "http://supplier-erp-mock:8000")).rstrip("/")
        self.batch_size = int(os.getenv("SUPPLIER_ERP_BATCH_SIZE", "25"))
        self.interval = float(os.getenv("SUPPLIER_ERP_POLL_SECONDS", "60"))

    async def poll_once(self) -> int:
        data = await self.request_json(f"{self.base_url}/supplier-events/{self.batch_size}")
        records = data if isinstance(data, list) else [data]
        for record in records:
            await self.publish_payload("supplier_event", record, endpoint=self.base_url)
        source_log(logging.INFO, self.source, "source_batch_published", count=len(records))
        return len(records)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                source_log(logging.ERROR, self.source, "source_cycle_failed", error=str(exc))
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass


class MqttIotConnector:
    source = "iot"

    def __init__(self, publisher: EventPublisher, broker: str | None = None, port: int | None = None) -> None:
        self.publisher = publisher
        self.broker = broker or os.getenv("MQTT_BROKER", "mosquitto")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.topic = os.getenv("MQTT_TOPIC", "suppliers/+/telemetry")
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        if reason_code == 0 or str(reason_code) == "Success":
            client.subscribe(self.topic)
            source_log(logging.INFO, self.source, "source_connected", topic=self.topic)
        else:
            source_log(logging.ERROR, self.source, "source_connection_failed", error=str(reason_code))

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("MQTT payload must be an object")
            publish = self.publisher.publish(
                IngestionEvent(
                    source=self.source,
                    event_type="sensor_telemetry",
                    payload=payload,
                    metadata={"mqtt_topic": msg.topic},
                )
            )
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is userdata:
                future = current_loop.create_task(publish)
            else:
                future = asyncio.run_coroutine_threadsafe(publish, userdata)
            future.add_done_callback(self._publish_done)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            source_log(logging.ERROR, self.source, "invalid_payload", error=str(exc), topic=msg.topic)
            event = IngestionEvent(
                source=self.source,
                event_type="invalid_sensor_telemetry",
                payload={"temperature": 0.0},
                metadata={"mqtt_topic": msg.topic, "raw_payload": msg.payload.decode("utf-8", errors="replace")},
            )
            try:
                current_loop = userdata
                future = asyncio.run_coroutine_threadsafe(self.publisher.publish_dlq(event, exc), current_loop)
                future.add_done_callback(self._publish_done)
            except (RuntimeError, TypeError) as publish_error:
                source_log(logging.ERROR, self.source, "dlq_publish_failed", error=str(publish_error), topic=msg.topic)

    def _publish_done(self, future: Any) -> None:
        try:
            future.result()
        except Exception as exc:
            source_log(logging.ERROR, self.source, "publish_failed", error=str(exc))

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.client.user_data_set(loop)
        try:
            self.client.connect(self.broker, self.port)
            self.client.loop_start()
            source_log(logging.INFO, self.source, "source_started", broker=self.broker)
        except Exception as exc:
            source_log(logging.ERROR, self.source, "source_start_failed", error=str(exc))

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


GDELTConnector = GdeltConnector
SupplierERPConnector = SupplierErpConnector
IoTMqttConnector = MqttIotConnector
