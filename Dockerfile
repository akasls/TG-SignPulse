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
    TZ=Asia/Shanghai

WORKDIR /app

# Install system runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copy python project definition and install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application source code
COPY backend/ ./backend/
COPY tg_signer/ ./tg_signer/
COPY tools/ ./tools/

# Copy built frontend assets to /web
COPY --from=frontend-builder /app/frontend/dist /web

# Create persistent data directory
RUN mkdir -p /data

EXPOSE 3000

VOLUME ["/data"]

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3000"]
