from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.cli.tasks import run_task_cli
from backend.core.config import get_settings
from backend.models.account import Account
from backend.models.task import Task
from backend.models.task_log import TaskLog

import time
import os

settings = get_settings()


def list_tasks(db: Session) -> List[Task]:
    return db.query(Task).order_by(Task.id.desc()).all()


def cleanup_old_logs(db: Session, days: int = 3) -> int:
    """清理超过指定天数的任务日志和文件"""
    cutoff = datetime.utcnow().timestamp() - (days * 24 * 3600)
    
    # 获取旧日志
    old_logs = db.query(TaskLog).filter(
        TaskLog.started_at < datetime.fromtimestamp(cutoff)
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


def run_task_once(db: Session, task: Task) -> TaskLog:
    account: Account = task.account  # type: ignore[assignment]
    log_file = _create_log_file(task)
    task_log = TaskLog(
        task_id=task.id,
        status="running",
        log_path=str(log_file),
        started_at=datetime.utcnow(),
    )
    db.add(task_log)
    db.commit()
    db.refresh(task_log)

    result = run_task_cli(account_name=account.account_name, task_name=task.name)

    task_log.finished_at = datetime.utcnow()
    task_log.output = (result.stdout or "") + "\n" + (result.stderr or "")
    task_log.status = "success" if result.returncode == 0 else "failed"
    db.commit()
    db.refresh(task_log)

    # write log file for long term storage
    try:
        with open(log_file, "w", encoding="utf-8") as fp:
            fp.write(task_log.output or "")
    except OSError:
        # best-effort, keep DB output at least
        pass

    task.last_run_at = task_log.finished_at
    db.commit()
    db.refresh(task)

    return task_log


def list_task_logs(db: Session, task_id: int, limit: int = 50) -> List[TaskLog]:
    return (
        db.query(TaskLog)
        .filter(TaskLog.task_id == task_id)
        .order_by(TaskLog.id.desc())
        .limit(limit)
        .all()
    )



