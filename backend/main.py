from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

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
from backend.core.database import (  # noqa: E402
    Base,
    get_engine,
    get_session_local,
    init_engine,
)
from backend.scheduler import (  # noqa: E402
    init_scheduler,
    shutdown_scheduler,
    sync_jobs,
)
from backend.services.users import ensure_admin  # noqa: E402
from backend.utils.paths import ensure_data_dirs  # noqa: E402
from tg_signer.async_utils import create_logged_task  # noqa: E402


# Silence /health check logs
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return (
            "/health" not in msg
            and "/healthz" not in msg
            and "/readyz" not in msg
        )


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")
app.state.ready = False

app.add_middleware(GZipMiddleware, minimum_size=1000)



app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由必须在静态文件挂载之前注册，并使用 /api 前缀
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
def health_checkz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def ready_check(response: Response) -> dict[str, str]:
    if app.state.ready:
        return {"status": "ready"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "starting"}


# 静态前端托管（Mode A: 单容器，FastAPI 提供静态文件）
web_dir = Path("/web")
if not web_dir.exists():
    local_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if local_dist.exists():
        web_dir = local_dist

next_static_dir = web_dir / "_next"
frontend_dev_url = os.getenv("FRONTEND_DEV_SERVER_URL", "http://127.0.0.1:3000")

if next_static_dir.exists():
    app.mount(
        "/_next",
        StaticFiles(directory=str(next_static_dir)),
        name="nextjs_static",
    )


# Catch-all 路由：处理所有前端路由，返回 index.html
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    SPA fallback: 对于所有非 API 路由，返回 index.html
    这样刷新页面时不会 404
    """
    # 检查是否是静态文件请求（严格防御路径穿越）
    if web_dir.exists():
        try:
            resolved_web = web_dir.resolve()
            file_path = (web_dir / full_path).resolve()
            if str(file_path).startswith(str(resolved_web)) and file_path.is_file():
                return FileResponse(file_path)

            html_path = (web_dir / f"{full_path}.html").resolve()
            if str(html_path).startswith(str(resolved_web)) and html_path.is_file():
                return FileResponse(html_path)

            index_path = resolved_web / "index.html"
            if index_path.exists() and index_path.is_file():
                return FileResponse(index_path)
        except Exception:
            pass

    # 如果 index.html 也不存在，开发模式下重定向到前端开发服务器，生产环境返回 404
    if os.getenv("FRONTEND_DEV_SERVER_URL"):
        normalized_path = full_path if full_path.startswith("/") else f"/{full_path}"
        if not normalized_path:
            normalized_path = "/"

        parsed_frontend = urlsplit(frontend_dev_url)
        redirect_target = urlunsplit(
            (
                parsed_frontend.scheme,
                parsed_frontend.netloc,
                normalized_path,
                "",
                "",
            )
        )
        return RedirectResponse(url=redirect_target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return Response(content="Not Found", status_code=status.HTTP_404_NOT_FOUND)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_data_dirs(settings)
    init_engine()
    Base.metadata.create_all(bind=get_engine())
    with get_session_local()() as db:
        ensure_admin(db)
    await init_scheduler(sync_on_startup=False)

    # Pre-export session strings from .session files to avoid SQLite locks during task execution
    _pre_export_session_strings()

    async def _post_startup() -> None:
        try:
            await sync_jobs()
            from backend.services.keyword_monitor import get_keyword_monitor_service

            await get_keyword_monitor_service().restart_from_tasks()
        except Exception as exc:
            logging.getLogger("backend.startup").error(
                f"Delayed scheduler sync failed: {exc}"
            )
        finally:
            app.state.ready = True

    app.state.startup_task = create_logged_task(
        _post_startup(),
        logger=logging.getLogger("backend.startup"),
        description="backend delayed startup sync",
    )


def _pre_export_session_strings() -> None:
    """Export session strings from all .session files at startup to enable in-memory mode."""
    from backend.utils.tg_session import (
        get_session_mode,
        load_session_string_file,
    )

    session_dir = settings.resolve_session_dir()
    logger = logging.getLogger("backend.startup")

    # Clean up any stray "*" directories (legacy bug from update_task wildcard handling)
    try:
        signs_dir = settings.resolve_workdir() / "signs"
        wildcard_dir = signs_dir / "*"
        if wildcard_dir.exists() and wildcard_dir.is_dir():
            import shutil
            shutil.rmtree(wildcard_dir)
            logger.info("Cleaned up stray '*' task directory")
    except Exception as exc:
        logger.warning(f"Failed to clean wildcard dir: {exc}")

    # Only needed in file mode - string mode already has session strings
    if get_session_mode() == "string":
        return

    # Export for all accounts that have .session files
    exported = 0
    for session_file in session_dir.glob("*.session"):
        account_name = session_file.stem
        # load_session_string_file will auto-export if .session_string doesn't exist
        result = load_session_string_file(session_dir, account_name)
        if result:
            exported += 1

    if exported:
        logger.info(f"Pre-exported {exported} session strings for in-memory task execution")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    startup_task = getattr(app.state, "startup_task", None)
    if startup_task is not None and not startup_task.done():
        startup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await startup_task
    shutdown_scheduler()
    try:
        from backend.services.keyword_monitor import get_keyword_monitor_service

        await get_keyword_monitor_service().stop()
    except Exception:
        pass
    try:
        from tg_signer.core import close_all_clients

        await close_all_clients()
    except Exception:
        pass
    from backend.utils.memory import trim_memory

    trim_memory()
