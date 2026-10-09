FROM python:3.12-slim
WORKDIR /app
COPY services/genai_engine/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/genai_engine services/genai_engine
CMD ["uvicorn", "services.genai_engine.app:app", "--host", "0.0.0.0", "--port", "8091"]
