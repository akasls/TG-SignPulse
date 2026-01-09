from __future__ import annotations

from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.task import Task
from backend.services.tasks import run_task_once

scheduler: BackgroundScheduler | None = None


def time_to_cron(time_str: str) -> str:
    """将 HH:MM 格式转换为 Cron 表达式 (0 MM HH * * *)"""
    if ":" not in time_str:
        return time_str  # 如果已经是 cron 格式则返回
    try:
        hour, minute = time_str.split(":")
        return f"{int(minute)} {int(hour)} * * *"
    except Exception:
        return time_str


def _job_run_task(task_id: int) -> None:
    db: Session = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or not task.enabled:
            return
        run_task_once(db, task)
    finally:
        db.close()


def _job_run_sign_task(account_name: str, task_name: str) -> None:
    """运行签到任务的 Job 包装器"""
    from backend.services.sign_tasks import sign_task_service
    try:
        print(f"Scheduler: 正在运行签到任务 {task_name} (账号: {account_name})")
        sign_task_service.run_task(account_name, task_name)
    except Exception as e:
        print(f"Scheduler: 运行签到任务 {task_name} 失败: {e}")


def _job_maintenance() -> None:
    """每日维护任务：清理旧日志等"""
    db: Session = SessionLocal()
    try:
        from backend.services.tasks import cleanup_old_logs
        from backend.services.sign_tasks import sign_task_service
        
        # 清理数据库任务日志
        count = cleanup_old_logs(db, days=3)
        print(f"Maintenance: 已清理 {count} 条数据库任务日志")
        
        # 清理签到任务日志 (SignTaskService 内部已有清理逻辑，但可以在此触发)
        sign_task_service._cleanup_old_logs()
        print("Maintenance: 已执行签到任务日志清理")
    except Exception as e:
        print(f"Maintenance Error: {e}")
    finally:
        db.close()


def sync_jobs() -> None:
    """
    Sync APScheduler jobs from DB tasks table and file-based sign tasks.
    """
    if scheduler is None:
        return
    
    from backend.services.sign_tasks import sign_task_service
    
    db: Session = SessionLocal()
    try:
        # 1. 同步数据库任务
        tasks = db.query(Task).all()
        existing_ids = set(j.id for j in scheduler.get_jobs())
        desired_ids = set()
        
        for task in tasks:
            job_id = f"task-{task.id}"
            desired_ids.add(job_id)
            if not task.enabled:
                if job_id in existing_ids:
                    scheduler.remove_job(job_id)
                continue
            
            try:
                trigger = CronTrigger.from_crontab(task.cron)
                if job_id in existing_ids:
                    scheduler.reschedule_job(job_id, trigger=trigger)
                else:
                    scheduler.add_job(
                        _job_run_task,
                        trigger=trigger,
                        id=job_id,
                        args=[task.id],
                        replace_existing=True,
                    )
            except Exception as e:
                print(f"Error scheduling DB task {task.id}: {e}")

        # 2. 同步签到任务 (SignTask)
        sign_tasks = sign_task_service.list_tasks()
        for st in sign_tasks:
            job_id = f"sign-{st['name']}"
            desired_ids.add(job_id)
            
            # SignTask 目前默认都是启用的，或者根据 st['enabled']
            if not st.get('enabled', True):
                if job_id in existing_ids:
                    scheduler.remove_job(job_id)
                continue
            
            try:
                cron = time_to_cron(st['sign_at'])
                trigger = CronTrigger.from_crontab(cron)
                if job_id in existing_ids:
                    scheduler.reschedule_job(job_id, trigger=trigger)
                else:
                    # 使用新的 job wrapper
                    scheduler.add_job(
                        _job_run_sign_task,
                        trigger=trigger,
                        id=job_id,
                        args=[st['account_name'], st['name']],
                        replace_existing=True,
                    )
            except Exception as e:
                print(f"Error scheduling sign task {st['name']}: {e}")

        # remove obsolete jobs
        for job_id in existing_ids - desired_ids:
            scheduler.remove_job(job_id)
    finally:
        db.close()


def init_scheduler() -> BackgroundScheduler:
    global scheduler
    if scheduler is None:
        from backend.core.config import get_settings
        settings = get_settings()
        scheduler = BackgroundScheduler(timezone=settings.timezone)
        scheduler.start()
        
        # 添加每日凌晨 3 点执行的维护任务
        scheduler.add_job(
            _job_maintenance,
            trigger=CronTrigger.from_crontab("0 3 * * *"),
            id="system-maintenance",
            replace_existing=True
        )
        
        sync_jobs()
    return scheduler


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None



