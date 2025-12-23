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
    PORT=3000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY . /app
# 安装项目及运行依赖（显式包含 uvicorn/fastapi 避免运行时缺失）
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir uvicorn fastapi

# 前端静态文件放在 /web，由 FastAPI StaticFiles 托管
RUN mkdir -p /web
COPY --from=frontend-builder /frontend/out /web

# 数据目录（通过 docker volume 映射到宿主机）
RUN mkdir -p /data

EXPOSE 3000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "3000"]


