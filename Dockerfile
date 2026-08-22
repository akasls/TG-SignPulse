# ==========================================
# Stage 1: Build Frontend (Vue 3 + Vite)
# ==========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Build & Run Backend (Python 3.12)
# ==========================================
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_DATA_DIR=/data \
    TZ=Asia/Shanghai \
    PORT=8080

WORKDIR /app

# Install system runtime & build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    ca-certificates \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata and source files required by setuptools
COPY pyproject.toml README.md LICENSE ./
COPY backend/ ./backend/
COPY tg_signer/ ./tg_signer/
COPY tools/ ./tools/

# Install python dependencies and package
RUN pip install --no-cache-dir .

# Copy built frontend assets to /web
COPY --from=frontend-builder /app/frontend/dist /web

# Create persistent data directory
RUN mkdir -p /data

EXPOSE 8080
EXPOSE 3000

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8080\")}/healthz').read()"

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
