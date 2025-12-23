from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.account import Account
from backend.models.task import Task
from backend.models.task_log import TaskLog
from backend.schemas.task import TaskCreate, TaskOut, TaskUpdate
from backend.schemas.task_log import TaskLogOut
from backend.scheduler import sync_jobs
from backend.services import tasks as task_service

router = APIRouter()


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return task_service.list_tasks(db)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    account = db.query(Account).filter(Account.id == payload.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    task = task_service.create_task(
        db,
        name=payload.name,
        cron=payload.cron,
        enabled=payload.enabled,
        account_id=payload.account_id,
    )
    sync_jobs()
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.account_id is not None:
        account = db.query(Account).filter(Account.id == payload.account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
    updated = task_service.update_task(
        db,
        task,
        name=payload.name,
        cron=payload.cron,
        enabled=payload.enabled,
        account_id=payload.account_id,
    )
    sync_jobs()
    return updated


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task_service.delete_task(db, task)
    sync_jobs()
    return {"ok": True}


@router.post("/{task_id}/run", response_model=TaskLogOut)
def run_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    log = task_service.run_task_once(db, task)
    return log


@router.get("/{task_id}/logs", response_model=list[TaskLogOut])
def list_logs(
    task_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    task = task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    logs = task_service.list_task_logs(db, task_id, limit=limit)
    return logs



