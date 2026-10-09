FROM python:3.11-slim

WORKDIR /app

COPY services/ingestion/requirements.txt requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY services/ingestion services/ingestion
COPY services/ingestion/schemas services/ingestion/schemas

CMD ["python", "-m", "services.ingestion.app"]