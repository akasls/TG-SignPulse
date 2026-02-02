FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# Copy dependency manifests first for better layer caching.
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS app

ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  PIP_NO_CACHE_DIR=1 \
  PORT=8080 \
  TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential tzdata && \
  rm -rf /var/lib/apt/lists/*

# Copy minimal metadata first for better layer caching.
COPY pyproject.toml ./
COPY tg_signer/__init__.py ./tg_signer/__init__.py

# Install core deps (FastAPI uses Pydantic v1 here).
RUN pip install --no-cache-dir "pydantic<2" "fastapi==0.109.2"

# Install bcrypt early to keep backend requirements consistent.
RUN pip install --no-cache-dir "bcrypt==4.0.1"

# Install project and runtime deps.
COPY . /app
RUN pip install --no-cache-dir . && \
  pip install --no-cache-dir \
  uvicorn[standard] \
  sqlalchemy \
  "passlib[bcrypt]==1.7.4" \
  "python-jose[cryptography]" \
  pyotp \
  qrcode[pil] \
  apscheduler \
  python-multipart

# Install tgcrypto only on amd64 to avoid arm64 build failures.
ARG TARGETPLATFORM
RUN if [ "${TARGETPLATFORM:-}" = "linux/amd64" ] || [ "$(uname -m)" = "x86_64" ]; then \
    pip install --no-cache-dir tgcrypto; \
  else \
    echo "Skipping tgcrypto on ${TARGETPLATFORM:-unknown}"; \
  fi

# Frontend static files served from /web.
RUN mkdir -p /web
COPY --from=frontend-builder /frontend/out /web

# Data dir (mapped via volume).
RUN mkdir -p /data

# Non-root user.
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd -r -g ${APP_GID} app && \
  useradd -r -u ${APP_UID} -g app -d /app -s /usr/sbin/nologin app && \
  chown -R app:app /data

EXPOSE 8080

# Healthcheck uses the PORT env var.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8080\")}/healthz').read()"

# Start with env-driven PORT (Zeabur sets this automatically).
USER app
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]