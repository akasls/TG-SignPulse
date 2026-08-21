from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from backend.core.auth import get_current_user
from backend.core.database import get_session_local
from backend.models.task_log import TaskLog

router = APIRouter()


async def _logs_event_stream(
    current_user,
    since_id: Optional[int] = None,
) -> AsyncGenerator[bytes, None]:
    if since_id is not None:
        last_id = since_id
    else:
        # Start from the latest log by default to avoid flooding client with historical logs
        session_local = get_session_local()
        db = session_local()
        try:
            latest = db.query(TaskLog.id).order_by(TaskLog.id.desc()).first()
            last_id = latest[0] if latest else 0
        finally:
            db.close()

    last_heartbeat = time.monotonic()
    try:
        while True:
            # Use a fresh session for each poll to avoid holding connections open
            session_local = get_session_local()
            db = session_local()
            try:
                logs = (
                    db.query(TaskLog)
                    .filter(TaskLog.id > last_id)
                    .order_by(TaskLog.id.asc())
                    .limit(100)
                    .all()
                )
                if logs:
                    for log in logs:
                        last_id = log.id
                        payload = {
                            "id": log.id,
                            "task_id": log.task_id,
                            "status": log.status,
                            "started_at": log.started_at.isoformat(),
                            "finished_at": log.finished_at.isoformat() if log.finished_at else None,
                        }
                        data = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        yield data.encode("utf-8")
                    last_heartbeat = time.monotonic()
                elif time.monotonic() - last_heartbeat >= 15:
                    yield b": keep-alive\n\n"
                    last_heartbeat = time.monotonic()
            finally:
                db.close()
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return


@router.get("/logs")
async def logs_events(
    since_id: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
):
    async def event_generator():
        async for chunk in _logs_event_stream(current_user, since_id=since_id):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
