"""
签到任务 API 路由
提供签到任务的 REST API
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator

from backend.core.auth import get_current_user
from backend.services.sign_tasks import sign_task_service

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
    sign_at: str = Field(..., description="签到时间（CRON 表达式）")
    chats: List[ChatConfig] = Field(..., description="Chat 配置列表")
    random_seconds: int = Field(0, description="随机延迟秒数")
    sign_interval: int = Field(1, description="签到间隔秒数")

    @validator('name')
    def name_must_be_valid_filename(cls, v):
        import re
        if not v or not v.strip():
            raise ValueError('任务名称不能为空')
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


class SignTaskOut(BaseModel):
    """签到任务输出"""
    name: str
    sign_at: str
    chats: List[Dict[str, Any]]
    random_seconds: int
    sign_interval: int
    enabled: bool


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
def list_sign_tasks(current_user=Depends(get_current_user)):
    """获取所有签到任务列表"""
    tasks = sign_task_service.list_tasks()
    return tasks


@router.post("", response_model=SignTaskOut, status_code=status.HTTP_201_CREATED)
def create_sign_task(
    payload: SignTaskCreate,
    current_user=Depends(get_current_user),
):
    """创建新的签到任务"""
    import traceback
    try:
        # 转换 chats 为字典列表
        chats_dict = [chat.dict() for chat in payload.chats]
        
        task = sign_task_service.create_task(
            task_name=payload.name,
            sign_at=payload.sign_at,
            chats=chats_dict,
            random_seconds=payload.random_seconds,
            sign_interval=payload.sign_interval,
        )
        return task
    except Exception as e:
        print(f"创建任务失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@router.get("/{task_name}", response_model=SignTaskOut)
def get_sign_task(
    task_name: str,
    current_user=Depends(get_current_user),
):
    """获取单个签到任务的详细信息"""
    task = sign_task_service.get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
    return task


@router.put("/{task_name}", response_model=SignTaskOut)
def update_sign_task(
    task_name: str,
    payload: SignTaskUpdate,
    current_user=Depends(get_current_user),
):
    """更新签到任务"""
    try:
        # 检查任务是否存在
        existing = sign_task_service.get_task(task_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
        
        # 转换 chats 为字典列表
        chats_dict = None
        if payload.chats is not None:
            chats_dict = [chat.dict() for chat in payload.chats]
        
        task = sign_task_service.update_task(
            task_name=task_name,
            sign_at=payload.sign_at,
            chats=chats_dict,
            random_seconds=payload.random_seconds,
            sign_interval=payload.sign_interval,
        )
        return task
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"更新任务失败: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")


@router.delete("/{task_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sign_task(
    task_name: str,
    current_user=Depends(get_current_user),
):
    """删除签到任务"""
    success = sign_task_service.delete_task(task_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
    return {"ok": True}


@router.post("/{task_name}/run", response_model=RunTaskResult)
def run_sign_task(
    task_name: str,
    account_name: str,
    current_user=Depends(get_current_user),
):
    """手动运行签到任务"""
    # 检查任务是否存在
    task = sign_task_service.get_task(task_name)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_name} 不存在")
    
    result = sign_task_service.run_task(account_name, task_name)
    return result


@router.get("/chats/{account_name}", response_model=List[ChatOut])
async def get_account_chats(
    account_name: str,
    current_user=Depends(get_current_user),
):
    """获取账号的 Chat 列表"""
    from pyrogram import Client
    from pyrogram.enums import ChatType
    from pathlib import Path
    from backend.core.config import get_settings
    import os
    
    settings = get_settings()
    
    # 获取 session 文件路径
    session_dir = Path(settings.data_dir) / "sessions"
    session_path = str(session_dir / account_name)
    
    # 检查 session 文件是否存在
    if not (session_dir / f"{account_name}.session").exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账号 {account_name} 不存在或未登录"
        )
    
    # 从环境变量获取 API credentials
    api_id = os.getenv("TG_API_ID", "611335")
    api_hash = os.getenv("TG_API_HASH", "d524b414d21f4d37f08684c1df41ac9c")
    
    # 创建客户端
    client = Client(
        name=session_path,
        api_id=int(api_id),
        api_hash=api_hash,
        in_memory=False,
    )
    
    chats = []
    
    try:
        await client.start()
        
        # 获取所有对话
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            
            # 返回群组、频道、私聊和机器人
            if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                chats.append({
                    "id": chat.id,
                    "title": chat.title,
                    "username": chat.username,
                    "type": chat.type.name.lower(),
                    "first_name": None,
                })
            # 机器人
            elif chat.type == ChatType.BOT:
                display_name = chat.first_name or ""
                if chat.last_name:
                    display_name += f" {chat.last_name}"
                
                full_name = f"🤖 {display_name}"
                chats.append({
                    "id": chat.id,
                    "title": full_name,  # 设置 title，前端优先显示
                    "username": chat.username,
                    "type": "bot",
                    "first_name": display_name,
                })
            # 私聊
            elif chat.type == ChatType.PRIVATE:
                display_name = chat.first_name or ""
                if chat.last_name:
                    display_name += f" {chat.last_name}"
                    
                chats.append({
                    "id": chat.id,
                    "title": display_name,  # 设置 title，前端优先显示
                    "username": chat.username,
                    "type": "private",
                    "first_name": display_name,
                })
        
        await client.stop()
        return chats
        
    except Exception as e:
        try:
            await client.stop()
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 Chat 列表失败: {str(e)}"
        )
