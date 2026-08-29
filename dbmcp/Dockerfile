FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KITCHEN_DB_PATH=/data/kitchen.db \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=18000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 18000

CMD ["uvicorn", "init_db:app", "--host", "0.0.0.0", "--port", "18000"]