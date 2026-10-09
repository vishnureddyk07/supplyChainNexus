FROM python:3.12-slim
WORKDIR /app
COPY services/graph/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/graph services/graph
CMD ["python", "-m", "services.graph.app"]
