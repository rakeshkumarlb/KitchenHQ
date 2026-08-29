FROM node:22-alpine AS frontend

WORKDIR /frontend
COPY chatui/package*.json ./
RUN npm install
COPY chatui/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=streamable_http \
    MCP_URL=http://dbmcp:18000/mcp \
    TZ=UTC

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY executivechef_agent /app/executivechef_agent
COPY chatui /app/chatui
COPY --from=frontend /frontend/dist /app/chatui/dist
WORKDIR /app/chatui
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
