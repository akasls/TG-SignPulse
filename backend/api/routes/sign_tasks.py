"""
签到任务 API 路由
提供签到任务的 REST API
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user, verify_token
from backend.core.database import get_db
from backend.services.sign_tasks import get_sign_task_service

router = APIRouter()


# Pydantic 模型定义


class ActionBase(BaseModel):
    """动作基类"""

    action: int = Field(..., description="动作类型")


class SendTextAction(ActionBase):
    """发送文本动作"""

    action: int = Field(1, description="动作类型：1=发送文本")
    text: str = Field(..., description="要发送的文本")


class SendDiceAction(ActionBase):
    """发送骰子动作"""

    action: int = Field(2, description="动作类型：2=发送骰子")
    dice: str = Field(..., description="骰子表情")


class ClickKeyboardAction(ActionBase):
    """点击键盘按钮动作"""

    action: int = Field(3, description="动作类型：3=点击按钮")
    text: str = Field(..., description="按钮文本")


class ChooseOptionByImageAction(ActionBase):
    """AI 图片识别动作"""

    action: int = Field(4, description="动作类型：4=AI 图片识别")


class ReplyByCalculationAction(ActionBase):
    """AI 计算题动作"""

    action: int = Field(5, description="动作类型：5=AI 计算题")


class ChatConfig(BaseModel):
    """Chat 配置"""

    chat_id: int = Field(..., description="Chat ID")
    name: str = Field("", description="Chat 名称")
    actions: List[Dict[str, Any]] = Field(..., description="动作列表")
    delete_after: Optional[int] = Field(None, description="删除延迟（秒）")
    action_interval: int = Field(1, description="动作间隔（秒）")


class SignTaskCreate(BaseModel):
    """创建签到任务请求"""

    name: str = Field(..., description="任务名称")
    account_name: str = Field(..., description="关联的账号名称")
    sign_at: str = Field(..., description="签到时间（CRON 表达式）")
    chats: List[ChatConfig] = Field(..., description="Chat 配置列表")
    random_seconds: int = Field(0, description="随机延迟秒数")
    sign_interval: Optional[int] = Field(
        None, description="签到间隔秒数，留空使用全局配置或随机 1-120 秒"
    )
    execution_mode: Optional[str] = Field("fixed", description="执行模式: fixed/range")
    range_start: Optional[str] = Field(None, description="随机范围开始时间")
    range_end: Optional[str] = Field(None, description="随机范围结束时间")

    @validator("name")
    def name_must_be_valid_filename(cls, v):
        import re

        if not v or not v.strip():
            raise ValueError("任务名称不能为空")
        # Windows 文件名非法字符检查
        invalid_chars = r'[<>:"/\\|?*]'
        if re.search(invalid_chars, v):
            raise ValueError('任务名称不能包含特殊字符: < > : " / \\ | ? *')
        return v


class SignTaskUpdate(BaseModel):
    """更新签到任务请求"""

    sign_at: Optional[str] = Field(None, description="签到时间（CRON 表达式）")
    chats: Optional[List[ChatConfig]] = Field(None, description="Chat 配置列表")
    random_seconds: Optional[int] = Field(None, description="随机延迟秒数")
    sign_interval: Optional[int] = Field(None, description="签到间隔秒数")
    execution_mode: Optional[str] = Field(None, description="执行模式: fixed/range")
    range_start: Optional[str] = Field(None, description="随机范围开始时间")
    range_end: Optional[str] = Field(None, description="随机范围结束时间")


class LastRunInfo(BaseModel):
    """最后执行信息"""

    time: str
    success: bool
    message: str = ""


class SignTaskOut(BaseModel):
    """签到任务输出"""

    name: str
    account_name: str = ""
    sign_at: str
    chats: List[Dict[str, Any]]
    random_seconds: int
    sign_interval: int
    enabled: bool
    last_run: Optional[LastRunInfo] = None
    execution_mode: Optional[str] = "fixed"
    range_start: Optional[str] = None
    range_end: Optional[str] = None


class ChatOut(BaseModel):
    """Chat 输出"""

    id: int
    title: Optional[str] = None
    username: Optional[str] = None
    type: str
    first_name: Optional[str] = None


class RunTaskResult(BaseModel):
    """运行任务结果"""

    success: bool
    output: str
    error: str


# API 路由


@router.get("", response_model=List[SignTaskOut])
def list_sign_tasks(
    account_name: Optional[str] = None, current_user=Depends(get_current_user)
):
    """
    获取所有签到任务列表

    Args:
        account_name: 可选，按账号名筛选任务
    """
    tasks = get_sign_task_service().list_tasks(account_name=account_name)
    return tasks


@router.post("", response_model=SignTaskOut, status_code=status.HTTP_201_CREATED)
async def create_sign_task(
    payload: SignTaskCreate,
    current_user=Depends(get_current_user),
):
    """创建新的签到任务"""
    import traceback

    try:
        # 转换 chats 为字典列表
        chats_dict = [chat.dict() for chat in payload.chats]

        task = get_sign_task_service().create_task(
            task_name=payload.name,
            account_name=payload.account_name,
            sign_at=payload.sign_at,
            chats=chats_dict,
            random_seconds=payload.random_seconds,
            sign_interval=payload.sign_interval,
            execution_mode=payload.execution_mode,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )

        # 同步调度器
        from backend.scheduler import sync_jobs

        await sync_jobs()

        return task
    except Exception as e:
        print(f"创建任务失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("/{task_name}", response_model=SignTaskOut)
def get_sign_task(
    task_name: str,
    account_name: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """获取单个签到任务的详细信息"""
    task = get_sign_task_service().get_task(task_name, account_name=account_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
    return task


@router.put("/{task_name}", response_model=SignTaskOut)
async def update_sign_task(
    task_name: str,
    payload: SignTaskUpdate,
    account_name: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """更新签到任务"""
    try:
        # 检查任务是否存在
        existing = get_sign_task_service().get_task(task_name, account_name=account_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")

        # 转换 chats 为字典列表
        chats_dict = None
        if payload.chats is not None:
            chats_dict = [chat.dict() for chat in payload.chats]

        task = get_sign_task_service().update_task(
            task_name=task_name,
            sign_at=payload.sign_at,
            chats=chats_dict,
            random_seconds=payload.random_seconds,
            sign_interval=payload.sign_interval,
            account_name=account_name or existing.get("account_name"),
            execution_mode=payload.execution_mode,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )

        # 同步调度器
        from backend.scheduler import sync_jobs

        await sync_jobs()

        return task
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"更新任务失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")


@router.delete("/{task_name}", status_code=status.HTTP_200_OK)
async def delete_sign_task(
    task_name: str,
    account_name: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """删除签到任务"""
    success = get_sign_task_service().delete_task(task_name, account_name=account_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")

    # 同步调度器
    from backend.scheduler import sync_jobs

    await sync_jobs()

    return {"ok": True}


@router.post("/{task_name}/run", response_model=RunTaskResult)
async def run_sign_task(
    task_name: str,
    account_name: str,
    current_user=Depends(get_current_user),
):
    """手动运行签到任务"""
    # 检查任务是否存在
    task = get_sign_task_service().get_task(task_name, account_name=account_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")

    result = await get_sign_task_service().run_task_with_logs(account_name, task_name)
    return result


@router.get("/{task_name}/logs", response_model=List[str])
def get_sign_task_logs(
    task_name: str,
    account_name: str | None = None,
    current_user=Depends(get_current_user),
):
    """获取正在运行任务的实时日志"""
    logs = get_sign_task_service().get_active_logs(task_name, account_name=account_name)
    return logs


@router.get("/chats/{account_name}", response_model=List[ChatOut])
async def get_account_chats(
    account_name: str,
    force_refresh: bool = False,
    current_user=Depends(get_current_user),
):
    """获取账号的 Chat 列表"""
    try:
        return await get_sign_task_service().get_account_chats(
            account_name, force_refresh=force_refresh
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取对话列表失败: {str(e)}")


@router.websocket("/ws/{task_name}")
async def sign_task_logs_ws(
    websocket: WebSocket,
    task_name: str,
    account_name: str | None = Query(None),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    WebSocket 实时推送签到任务日志
    """
    # 验证 Token
    try:
        user = verify_token(token, db)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    last_idx = 0
    try:
        while True:
            # 获取当前所有日志
            active_logs = get_sign_task_service().get_active_logs(
                task_name, account_name=account_name
            )

            # 如果有新内容，则推送
            if len(active_logs) > last_idx:
                new_logs = active_logs[last_idx:]
                await websocket.send_json(
                    {
                        "type": "logs",
                        "data": new_logs,
                        "is_running": get_sign_task_service().is_task_running(
                            task_name, account_name=account_name
                        ),
                    }
                )
                last_idx = len(active_logs)

            # 如果任务已结束且日志已推完
            if (
                not get_sign_task_service().is_task_running(
                    task_name, account_name=account_name
                )
                and last_idx >= len(active_logs)
            ):
                await websocket.send_json({"type": "done", "is_running": False})
                break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WS Error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
