from __future__ import annotations
import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.cli.tasks import async_run_task_cli
from backend.core.config import get_settings
from backend.models.account import Account
from backend.models.task import Task
from backend.models.task_log import TaskLog

settings = get_settings()

# 用于实时日志推送的状态跟踪
_active_tasks: dict[int, bool] = {}
_active_logs: dict[int, list[str]] = {}

def get_active_logs(task_id: int) -> list[str]:
    return _active_logs.get(task_id, [])

def is_task_running(task_id: int) -> bool:
    return _active_tasks.get(task_id, False)


def list_tasks(db: Session) -> List[Task]:
    return db.query(Task).order_by(Task.id.desc()).all()


def cleanup_old_logs(db: Session, days: int = 3) -> int:
    """清理超过指定天数的任务日志和文件"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # 获取旧日志
    old_logs = db.query(TaskLog).filter(
        TaskLog.started_at < cutoff
    ).all()
    
    count = 0
    for log in old_logs:
        # 删除文件
        if log.log_path:
            try:
                p = Path(log.log_path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        # 从数据库删除
        db.delete(log)
        count += 1
    
    if count > 0:
        db.commit()
    return count


def get_task(db: Session, task_id: int) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def create_task(
    db: Session,
    name: str,
    cron: str,
    enabled: bool,
    account_id: int,
) -> Task:
    task = Task(name=name, cron=cron, enabled=enabled, account_id=account_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task(
    db: Session,
    task: Task,
    *,
    name: Optional[str] = None,
    cron: Optional[str] = None,
    enabled: Optional[bool] = None,
    account_id: Optional[int] = None,
) -> Task:
    if name is not None:
        task.name = name
    if cron is not None:
        task.cron = cron
    if enabled is not None:
        task.enabled = enabled
    if account_id is not None:
        task.account_id = account_id
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    db.delete(task)
    db.commit()


def _create_log_file(task: Task) -> Path:
    logs_dir = settings.resolve_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return logs_dir / f"task_{task.id}_{ts}.log"




async def run_task_once(db: Session, task: Task) -> TaskLog:
    if is_task_running(task.id):
        # 如果已经在运行，返回最新的运行记录（或者抛出异常）
        last_log = db.query(TaskLog).filter(TaskLog.task_id == task.id).order_by(TaskLog.id.desc()).first()
        return last_log

    account: Account = task.account  # type: ignore[assignment]
    log_file = _create_log_file(task)
    
    _active_tasks[task.id] = True
    _active_logs[task.id] = []

    task_log = TaskLog(
        task_id=task.id,
        status="running",
        log_path=str(log_file),
        started_at=datetime.utcnow(),
    )
    db.add(task_log)
    db.commit()
    db.refresh(task_log)

    def log_callback(line: str):
        _active_logs[task.id].append(line)
        if len(_active_logs[task.id]) > 500:
            _active_logs[task.id].pop(0)

    try:
        # 使用异步执行调用，并注入回调
        returncode, stdout, stderr = await async_run_task_cli(
            account_name=account.account_name, 
            task_name=task.name,
            callback=log_callback
        )

        full_output = (stdout or "") + "\n" + (stderr or "")
        
        # 写入日志文件（完整内容）
        with open(log_file, "w", encoding="utf-8") as fp:
            fp.write(full_output)

        # 更新数据库记录
        task_log.finished_at = datetime.utcnow()
        task_log.status = "success" if returncode == 0 else "failed"
        if returncode != 0:
            task_log.output = stderr[-1000:] if stderr else "Failed with exit code " + str(returncode)
        else:
            task_log.output = "Success"
            
        db.commit()
        db.refresh(task_log)

        task.last_run_at = task_log.finished_at
        db.commit()
    except Exception as e:
        msg = f"Error running task: {e}"
        _active_logs[task.id].append(msg)
        task_log.status = "failed"
        task_log.output = msg[-1000:]
        db.commit()
    finally:
        _active_tasks[task.id] = False
        # 延迟清理日志
        async def cleanup():
            await asyncio.sleep(60)
            if not is_task_running(task.id):
                _active_logs.pop(task.id, None)
        asyncio.create_task(cleanup())

    return task_log


def list_task_logs(db: Session, task_id: int, limit: int = 50) -> List[TaskLog]:
    return (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task_id)
        .order_by(TaskLog.id.desc())
        .limit(limit)
        .all()
    )



