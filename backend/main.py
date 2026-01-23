from __future__ import annotations

import logging
import sqlite3

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Monkeypatch sqlite3.connect to increase default timeout
_original_sqlite3_connect = sqlite3.connect


def _patched_sqlite3_connect(*args, **kwargs):
    # Force timeout to be at least 10 seconds, even if Pyrogram sets it to 1
    if "timeout" in kwargs:
        if kwargs["timeout"] < 10:
            kwargs["timeout"] = 10
    else:
        kwargs["timeout"] = 30
    return _original_sqlite3_connect(*args, **kwargs)


sqlite3.connect = _patched_sqlite3_connect

from backend.api import router as api_router  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.core.database import Base, SessionLocal, engine  # noqa: E402
from backend.scheduler import init_scheduler, shutdown_scheduler  # noqa: E402
from backend.services.users import ensure_admin  # noqa: E402
from backend.utils.paths import ensure_data_dirs  # noqa: E402


# Silence /health check logs
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由必须在静态文件挂载之前注册，并使用 /api 前缀
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


# 静态前端托管（Mode A: 单容器，FastAPI 提供静态文件）
# 挂载 Next.js 静态资源
# app.mount(
#     "/_next",
#     StaticFiles(directory="/web/_next"),
#     name="nextjs_static",
# )


# Catch-all 路由：处理所有前端路由，返回 index.html
# @app.get("/{full_path:path}")
# async def serve_spa(full_path: str):
#     """
#     SPA fallback: 对于所有非 API 路由，返回 index.html
#     这样刷新页面时不会 404
#     """
#     # 检查是否是静态文件请求
#     web_dir = Path("/web")
#     file_path = web_dir / full_path
#
#     # 如果文件存在且不是目录，直接返回文件
#     if file_path.exists() and file_path.is_file():
#         return FileResponse(file_path)
#
#     # 尝试添加 .html 后缀（Next.js 导出通常会生成 .html 文件）
#     html_path = web_dir / f"{full_path}.html"
#     if html_path.exists() and html_path.is_file():
#         return FileResponse(html_path)
#
#     # 否则返回 index.html（SPA 路由）
#     index_path = web_dir / "index.html"
#     if index_path.exists():
#         return FileResponse(index_path)
#
#     # 如果 index.html 也不存在，返回 404
#     return {"detail": "Frontend not built"}


@app.on_event("startup")
async def on_startup() -> None:
    ensure_data_dirs(settings)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_admin(db)
    await init_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    shutdown_scheduler()
