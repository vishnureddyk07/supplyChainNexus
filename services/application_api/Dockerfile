FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-risk.txt requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-risk.txt

COPY supplychain_nexus /app/supplychain_nexus
COPY services/application_api /app/services/application_api
COPY services/event_consumer /app/services/event_consumer
COPY services/demo /app/services/demo
COPY services/graph /app/services/graph
COPY services/risk /app/services/risk

ENV PYTHONPATH=/app
EXPOSE 8001

CMD ["uvicorn", "services.application_api.app:app", "--host", "0.0.0.0", "--port", "8001"]
