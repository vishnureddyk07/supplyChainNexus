FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY supplychain_nexus /app/supplychain_nexus
COPY supplier-erp-mock /app/supplier-erp-mock

ENV PYTHONPATH=/app
WORKDIR /app/supplier-erp-mock

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
