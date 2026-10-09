FROM python:3.12-slim
WORKDIR /app
COPY services/backend_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/backend_api services/backend_api
CMD ["uvicorn", "services.backend_api.app:app", "--host", "0.0.0.0", "--port", "8001"]
