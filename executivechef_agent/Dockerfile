FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable_http \
    MCP_URL=http://localhost:18000/mcp \
    TZ=UTC

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py prompt.md worker.py .env.example ./
CMD ["python", "agent.py"]