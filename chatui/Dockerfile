FROM node:22-alpine AS frontend

WORKDIR /frontend
COPY package*.json ./
RUN npm install
COPY . ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY --from=frontend /frontend/dist ./dist

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
