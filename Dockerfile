FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# 先拷贝依赖清单，避免锁文件不存在导致 COPY 失败，使用通配符覆盖 package.json / package-lock.json
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

# 先复制 pyproject.toml 和相关配置文件
COPY pyproject.toml ./
COPY tg_signer/__init__.py ./tg_signer/__init__.py

# 安装核心依赖，固定 pydantic<2 且 fastapi 使用 v1 兼容版本
RUN pip install --no-cache-dir "pydantic<2" "fastapi==0.109.2"

# 先安装 bcrypt，确保使用正确的后端
RUN pip install --no-cache-dir "bcrypt==4.0.1"

# 安装项目及其余运行依赖
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
  python-multipart \
  tgcrypto

# 前端静态文件放在 /web，由 FastAPI StaticFiles 托管
RUN mkdir -p /web
COPY --from=frontend-builder /frontend/out /web

# 数据目录（通过 docker volume 映射到宿主机）
RUN mkdir -p /data

# 非 root 运行
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd -r -g ${APP_GID} app && \
  useradd -r -u ${APP_UID} -g app -d /app -s /usr/sbin/nologin app && \
  chown -R app:app /data

EXPOSE 8080

# 健康检查 - 使用环境变量 PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8080\")}/healthz').read()"

# 使用环境变量 PORT 启动，Zeabur 会自动设置此变量
USER app
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]


