# Stage 1 — build React frontend
FROM node:20-alpine AS frontend-build

WORKDIR /build

COPY app/frontend/package*.json ./
RUN npm ci

COPY app/frontend/ ./
RUN npm run build

# Stage 2 — Python backend
FROM python:3.12-slim

WORKDIR /app

COPY app/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/backend/ ./

# Copy built frontend static files
COPY --from=frontend-build /build/dist ./static

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
