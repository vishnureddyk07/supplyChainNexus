FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY supplychain_nexus /app/supplychain_nexus
COPY services/event_consumer /app/services/event_consumer
COPY services/graph /app/services/graph

ENV PYTHONPATH=/app

CMD ["python", "-m", "services.event_consumer.app"]
