FROM python:3.12-slim
WORKDIR /app
COPY services/risk_engine/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt neo4j==5.27.0 fastapi==0.115.6 uvicorn==0.34.0
COPY services/risk_engine services/risk_engine
CMD ["uvicorn", "services.risk_engine.app:app", "--host", "0.0.0.0", "--port", "8090"]
