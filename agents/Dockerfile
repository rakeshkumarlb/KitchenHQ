FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable_http \
    MCP_URL=http://dbmcp:18000/mcp \
    TZ=UTC

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# `app/` includes app/email/ (outbound mail). SMTP_* env is optional - passed through
# by docker-compose from the root .env; unset just disables sending.
COPY app ./app
COPY prompts ./prompts
COPY cli.py .env.example ./

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8090"]
