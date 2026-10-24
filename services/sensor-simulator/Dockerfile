FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY supplychain_nexus /app/supplychain_nexus
COPY services/sensor-simulator/simulator.py /app/simulator.py

ENV PYTHONPATH=/app

CMD ["python", "/app/simulator.py"]