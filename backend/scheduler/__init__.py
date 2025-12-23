from __future__ import annotations

from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.task import Task
from backend.services.tasks import run_task_once

scheduler: BackgroundScheduler | None = None


def _job_run_task(task_id: int) -> None:
    db: Session = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or not task.enabled:
            return
        run_task_once(db, task)
    finally:
        db.close()


def sync_jobs() -> None:
    """
    Sync APScheduler jobs from DB tasks table.
    """
    if scheduler is None:
        return
    db: Session = SessionLocal()
    try:
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
        # remove obsolete jobs
        for job_id in existing_ids - desired_ids:
            scheduler.remove_job(job_id)
    finally:
        db.close()


def init_scheduler() -> BackgroundScheduler:
    global scheduler
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        sync_jobs()
    return scheduler


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None



