FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

# 先拷贝依赖清单，避免锁文件不存在导致 COPY 失败，使用通配符覆盖 package.json / package-lock.json
COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS app

ENV PYTHONUNBUFFERED=1 \
  PIP_NO_CACHE_DIR=1 \
  PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libssl-dev \
  libffi-dev \
  python3-dev \
  cargo \
  pkg-config && \
  rm -rf /var/lib/apt/lists/*

# 先复制 pyproject.toml 和相关配置文件
COPY pyproject.toml ./
COPY tg_signer/__init__.py ./tg_signer/__init__.py

# 安装核心依赖
# fix: pin setuptools<70.0.0 to avoid "AttributeError: cython_sources" in pyrogram/tgcrypto builds
RUN pip install --no-cache-dir "setuptools<70.0.0" "wheel" "Cython<3"
# 固定 pydantic<2 且 fastapi 使用 v1 兼容版本. Ensure typing_extensions is new enough for fastapi.
RUN pip install --no-cache-dir "pydantic<2" "fastapi==0.109.2" "typing_extensions>=4.8.0"

# 先安装 bcrypt，确保使用正确的后端
RUN pip install --no-cache-dir "bcrypt==4.0.1"

# 安装项目及其余运行依赖
COPY . /app
# Remove redundant args that are already in pyproject.toml
RUN pip install --no-cache-dir --no-build-isolation . && \
  pip install --no-cache-dir \
  uvicorn[standard] \
  "python-jose[cryptography]" \
  pyotp \
  qrcode[pil] \
  apscheduler \
  python-multipart && \
  pip install --no-cache-dir --upgrade "typing_extensions>=4.8.0"

# 前端静态文件放在 /web，由 FastAPI StaticFiles 托管
RUN mkdir -p /web
COPY --from=frontend-builder /frontend/out /web

# 数据目录（通过 docker volume 映射到宿主机）
RUN mkdir -p /data

EXPOSE 8080

# 健康检查 - 使用环境变量 PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8080\")}/health').read()"

# 使用环境变量 PORT 启动，Zeabur 会自动设置此变量
CMD sh -c "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --loop asyncio"


