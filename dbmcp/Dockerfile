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
# Pre-warm the local embedding model into the image itself (NOT /data - that path is a
# host bind mount at runtime, so anything baked there during the build gets shadowed by
# the empty host directory and would silently re-download anyway). FASTEMBED_CACHE_PATH
# is set to this same image-local path so the runtime model load in
# kitchendb/embeddings.py finds what was pre-warmed here, with zero network calls.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir=os.environ['FASTEMBED_CACHE_PATH'])"

COPY . .

RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 18000

CMD ["uvicorn", "init_db:app", "--host", "0.0.0.0", "--port", "18000"]