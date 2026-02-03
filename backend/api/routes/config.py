"""
配置管理 API 路由
提供任务配置的导入导出功能
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.models.user import User
from backend.services.config import get_config_service

router = APIRouter()


# ============ Schemas ============


class ExportTaskResponse(BaseModel):
    """导出任务响应"""

    task_name: str
    task_type: str
    config_json: str


class ImportTaskRequest(BaseModel):
    """导入任务请求"""

    config_json: str
    task_name: Optional[str] = None  # 新任务名称（可选）
    account_name: Optional[str] = None  # 新账号名称（可选）


class ImportTaskResponse(BaseModel):
    """导入任务响应"""

    success: bool
    task_name: str
    message: str


class ImportAllRequest(BaseModel):
    """导入所有配置请求"""

    config_json: str
    overwrite: bool = False  # 是否覆盖已存在的配置


class ImportAllResponse(BaseModel):
    """导入所有配置响应"""

    signs_imported: int
    signs_skipped: int
    monitors_imported: int
    monitors_skipped: int
    errors: list[str]
    message: str


class TaskListResponse(BaseModel):
    """任务列表响应"""

    sign_tasks: list[str]
    monitor_tasks: list[str]
    total: int


# ============ API Routes ============


@router.get("/tasks", response_model=TaskListResponse)
def list_all_tasks(current_user: User = Depends(get_current_user)):
    """
    获取所有任务列表（签到任务和监控任务）
    """
    try:
        sign_tasks = get_config_service().list_sign_tasks()
        monitor_tasks = get_config_service().list_monitor_tasks()

        return TaskListResponse(
            sign_tasks=sign_tasks,
            monitor_tasks=monitor_tasks,
            total=len(sign_tasks) + len(monitor_tasks),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}",
        )


@router.get("/export/sign/{task_name}")
def export_sign_task(
    task_name: str,
    account_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    导出单个签到任务配置

    返回 JSON 格式的配置文件，可以保存后导入
    """
    try:
        config_json = get_config_service().export_sign_task(
            task_name, account_name=account_name
        )

        if config_json is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"任务 {task_name} 不存在"
            )

        from fastapi import Response

        # 返回 JSON 响应，设置下载文件名
        return Response(
            content=config_json,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{task_name}_config.json"'
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出任务失败: {str(e)}",
        )


@router.post("/import/sign", response_model=ImportTaskResponse)
def import_sign_task(
    request: ImportTaskRequest, current_user: User = Depends(get_current_user)
):
    """
    导入签到任务配置

    可以指定新的任务名称，如果不指定则使用原名称
    """
    try:
        success = get_config_service().import_sign_task(
            request.config_json, request.task_name, request.account_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="导入失败，配置格式无效"
            )

        # 确定最终的任务名称
        import json

        data = json.loads(request.config_json)
        final_task_name = request.task_name or data.get("task_name", "imported_task")

        # 同步调度器
        from backend.scheduler import sync_jobs

        sync_jobs()

        return ImportTaskResponse(
            success=True,
            task_name=final_task_name,
            message=f"任务 {final_task_name} 导入成功",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入任务失败: {str(e)}",
        )


@router.get("/export/all")
def export_all_configs(current_user: User = Depends(get_current_user)):
    """
    导出所有配置（签到任务和监控任务）

    返回包含所有配置的 JSON 文件
    """
    try:
        config_json = get_config_service().export_all_configs()

        from fastapi import Response

        # 返回 JSON 响应，设置下载文件名
        return Response(
            content=config_json,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="tg_signer_all_configs.json"'
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出所有配置失败: {str(e)}",
        )


@router.post("/import/all", response_model=ImportAllResponse)
def import_all_configs(
    request: ImportAllRequest, current_user: User = Depends(get_current_user)
):
    """
    导入所有配置

    可以选择是否覆盖已存在的配置
    """
    try:
        result = get_config_service().import_all_configs(
            request.config_json, request.overwrite
        )

        # 构建消息
        message_parts = []
        if result["signs_imported"] > 0:
            message_parts.append(f"导入了 {result['signs_imported']} 个签到任务")
        if result["signs_skipped"] > 0:
            message_parts.append(f"跳过了 {result['signs_skipped']} 个已存在的签到任务")
        if result["monitors_imported"] > 0:
            message_parts.append(f"导入了 {result['monitors_imported']} 个监控任务")
        if result["monitors_skipped"] > 0:
            message_parts.append(
                f"跳过了 {result['monitors_skipped']} 个已存在的监控任务"
            )

        message = "，".join(message_parts) if message_parts else "没有导入任何配置"

        # 同步调度器
        from backend.scheduler import sync_jobs

        sync_jobs()

        return ImportAllResponse(**result, message=message)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入所有配置失败: {str(e)}",
        )


@router.delete("/sign/{task_name}")
def delete_sign_task(
    task_name: str,
    account_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    删除签到任务配置

    注意：删除后无法恢复
    """
    try:
        success = get_config_service().delete_sign_config(
            task_name, account_name=account_name
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"任务 {task_name} 不存在"
            )

        # 同步调度器
        from backend.scheduler import sync_jobs

        sync_jobs()

        return {"success": True, "message": f"任务 {task_name} 已删除"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除任务失败: {str(e)}",
        )


# ============ AI 配置 ============


class AIConfigRequest(BaseModel):
    """AI 配置请求"""

    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None


class AIConfigResponse(BaseModel):
    """AI 配置响应"""

    has_config: bool
    base_url: Optional[str] = None
    model: Optional[str] = None
    # 不返回 api_key，只返回部分遮蔽的版本
    api_key_masked: Optional[str] = None


class AIConfigSaveResponse(BaseModel):
    """保存 AI 配置响应"""

    success: bool
    message: str


class AITestResponse(BaseModel):
    """测试 AI 连接响应"""

    success: bool
    message: str
    model_used: Optional[str] = None


@router.get("/ai", response_model=AIConfigResponse)
def get_ai_config(current_user: User = Depends(get_current_user)):
    """
    获取 AI 配置（不返回完整的 API Key）
    """
    try:
        config = get_config_service().get_ai_config()

        if not config:
            return AIConfigResponse(has_config=False)

        # 遮蔽 API Key
        api_key = config.get("api_key", "")
        if api_key:
            masked = (
                api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
                if len(api_key) > 8
                else "****"
            )
        else:
            masked = None

        return AIConfigResponse(
            has_config=True,
            base_url=config.get("base_url"),
            model=config.get("model"),
            api_key_masked=masked,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 AI 配置失败: {str(e)}",
        )


@router.post("/ai", response_model=AIConfigSaveResponse)
def save_ai_config(
    request: AIConfigRequest, current_user: User = Depends(get_current_user)
):
    """
    保存 AI 配置
    """
    try:
        get_config_service().save_ai_config(
            api_key=request.api_key, base_url=request.base_url, model=request.model
        )

        return AIConfigSaveResponse(success=True, message="AI 配置已保存")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存 AI 配置失败: {str(e)}",
        )


@router.post("/ai/test", response_model=AITestResponse)
async def test_ai_connection(current_user: User = Depends(get_current_user)):
    """
    测试 AI 连接
    """
    try:
        result = await get_config_service().test_ai_connection()
        return AITestResponse(**result)

    except Exception as e:
        return AITestResponse(success=False, message=f"测试失败: {str(e)}")


@router.delete("/ai", response_model=AIConfigSaveResponse)
def delete_ai_config(current_user: User = Depends(get_current_user)):
    """
    删除 AI 配置
    """
    try:
        get_config_service().delete_ai_config()

        return AIConfigSaveResponse(success=True, message="AI 配置已删除")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除 AI 配置失败: {str(e)}",
        )


# ============ 全局设置 ============


class GlobalSettingsRequest(BaseModel):
    """全局设置请求"""

    sign_interval: Optional[int] = None  # None 表示随机 1-120 秒
    log_retention_days: int = 7  # 日志保留天数，默认 7


class GlobalSettingsResponse(BaseModel):
    """全局设置响应"""

    sign_interval: Optional[int] = None
    log_retention_days: int = 7


@router.get("/settings", response_model=GlobalSettingsResponse)
def get_global_settings(current_user: User = Depends(get_current_user)):
    """
    获取全局设置
    """
    try:
        settings = get_config_service().get_global_settings()
        return GlobalSettingsResponse(**settings)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取全局设置失败: {str(e)}",
        )


@router.post("/settings", response_model=AIConfigSaveResponse)
def save_global_settings(
    request: GlobalSettingsRequest, current_user: User = Depends(get_current_user)
):
    """
    保存全局设置
    """
    try:
        settings = {
            "sign_interval": request.sign_interval,
            "log_retention_days": request.log_retention_days,
        }
        get_config_service().save_global_settings(settings)

        return AIConfigSaveResponse(success=True, message="全局设置已保存")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存全局设置失败: {str(e)}",
        )


# ============ Telegram API 配置 ============


class TelegramConfigRequest(BaseModel):
    """Telegram API 配置请求"""

    api_id: str
    api_hash: str


class TelegramConfigResponse(BaseModel):
    """Telegram API 配置响应"""

    api_id: str
    api_hash: str
    is_custom: bool  # 是否为自定义配置
    # 默认值（用于 UI 显示）
    default_api_id: str
    default_api_hash: str


class TelegramConfigSaveResponse(BaseModel):
    """保存 Telegram API 配置响应"""

    success: bool
    message: str


@router.get("/telegram", response_model=TelegramConfigResponse)
def get_telegram_config(current_user: User = Depends(get_current_user)):
    """
    获取 Telegram API 配置

    返回当前配置（可能是默认值或自定义值）
    """
    try:
        config = get_config_service().get_telegram_config()

        return TelegramConfigResponse(
            api_id=config.get("api_id", ""),
            api_hash=config.get("api_hash", ""),
            is_custom=config.get("is_custom", False),
            default_api_id=get_config_service().DEFAULT_TG_API_ID,
            default_api_hash=get_config_service().DEFAULT_TG_API_HASH,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取 Telegram API 配置失败: {str(e)}",
        )


@router.post("/telegram", response_model=TelegramConfigSaveResponse)
def save_telegram_config(
    request: TelegramConfigRequest, current_user: User = Depends(get_current_user)
):
    """
    保存 Telegram API 配置

    设置自定义的 API ID 和 API Hash
    """
    try:
        # 验证输入
        if not request.api_id or not request.api_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API ID 和 API Hash 不能为空",
            )

        success = get_config_service().save_telegram_config(
            api_id=request.api_id, api_hash=request.api_hash
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="保存配置失败"
            )

        return TelegramConfigSaveResponse(
            success=True, message="Telegram API 配置已保存"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存 Telegram API 配置失败: {str(e)}",
        )


@router.delete("/telegram", response_model=TelegramConfigSaveResponse)
def reset_telegram_config(current_user: User = Depends(get_current_user)):
    """
    重置 Telegram API 配置（恢复默认）
    """
    try:
        get_config_service().reset_telegram_config()

        return TelegramConfigSaveResponse(
            success=True, message="Telegram API 配置已重置为默认值"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重置 Telegram API 配置失败: {str(e)}",
        )
