"""
账号管理 API 路由（重构版）
基于原项目逻辑，使用手机号登录
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.core.rate_limit import compose_rate_limit_key, get_rate_limiter
from backend.models.user import User
from backend.services.telegram import get_telegram_service
from backend.utils.names import validate_storage_name
from backend.utils.task_logs import extract_last_target_message

router = APIRouter()
logger = logging.getLogger("backend.qr_login")
rate_limiter = get_rate_limiter()


def _apply_rate_limit(
    scope: str,
    request: Request,
    detail: str,
    *parts: str,
    max_attempts: int,
    window_seconds: int,
    block_seconds: int,
) -> str:
    key = compose_rate_limit_key(request, *parts)
    rate_limiter.hit(
        scope=scope,
        key=key,
        max_attempts=max_attempts,
        window_seconds=window_seconds,
        block_seconds=block_seconds,
        detail=detail,
    )
    return key


# ============ Schemas ============


class LoginStartRequest(BaseModel):
    """开始登录请求"""

    account_name: str
    phone_number: str
    proxy: Optional[str] = None


class LoginStartResponse(BaseModel):
    """开始登录响应"""

    phone_code_hash: str
    phone_number: str
    account_name: str
    message: str = "验证码已发送到您的手机"


class LoginVerifyRequest(BaseModel):
    """验证登录请求"""

    account_name: str
    phone_number: str
    phone_code: str
    phone_code_hash: str
    password: Optional[str] = None  # 2FA 密码
    proxy: Optional[str] = None


class LoginVerifyResponse(BaseModel):
    """验证登录响应"""

    success: bool
    user_id: Optional[int] = None
    first_name: Optional[str] = None
    username: Optional[str] = None
    message: str


class QrLoginStartRequest(BaseModel):
    """扫码登录请求"""

    account_name: str
    proxy: Optional[str] = None


class QrLoginStartResponse(BaseModel):
    """扫码登录开始响应"""

    login_id: str
    qr_uri: str
    qr_image: Optional[str] = None
    expires_at: str


class AccountInfo(BaseModel):
    """账号信息"""

    name: str
    session_file: str
    exists: bool
    size: int
    remark: Optional[str] = None
    proxy: Optional[str] = None
    status: str = "connected"
    status_message: Optional[str] = None
    status_code: Optional[str] = None
    status_checked_at: Optional[str] = None
    needs_relogin: bool = False


class QrLoginStatusResponse(BaseModel):
    """扫码登录状态响应"""

    status: str
    expires_at: Optional[str] = None
    message: Optional[str] = None
    account: Optional[AccountInfo] = None
    user_id: Optional[int] = None
    first_name: Optional[str] = None
    username: Optional[str] = None


class QrLoginCancelRequest(BaseModel):
    """扫码登录取消请求"""

    login_id: str


class QrLoginCancelResponse(BaseModel):
    """扫码登录取消响应"""

    success: bool
    message: str


class QrLoginPasswordRequest(BaseModel):
    """扫码登录 2FA 密码请求"""

    login_id: str
    password: str


class QrLoginPasswordResponse(BaseModel):
    """扫码登录 2FA 密码响应"""

    success: bool
    message: str
    account: Optional[AccountInfo] = None
    user_id: Optional[int] = None
    first_name: Optional[str] = None
    username: Optional[str] = None


class AccountListResponse(BaseModel):
    """账号列表响应"""

    accounts: list[AccountInfo]
    total: int


class DeleteAccountResponse(BaseModel):
    """删除账号响应"""

    success: bool
    message: str


class AccountUpdateRequest(BaseModel):
    new_account_name: Optional[str] = None
    """更新账号备注/代理"""

    remark: Optional[str] = None
    proxy: Optional[str] = None


class AccountUpdateResponse(BaseModel):
    """更新账号响应"""

    success: bool
    message: str
    account: Optional[AccountInfo] = None


class AccountStatusCheckRequest(BaseModel):
    """批量账号状态检测请求"""

    account_names: Optional[list[str]] = None
    timeout_seconds: float = 6.0


class AccountStatusItem(BaseModel):
    """账号状态检测结果"""

    account_name: str
    ok: bool
    status: str
    message: str = ""
    code: Optional[str] = None
    checked_at: Optional[str] = None
    needs_relogin: bool = False
    user_id: Optional[int] = None


class AccountStatusCheckResponse(BaseModel):
    """批量账号状态检测响应"""

    results: list[AccountStatusItem]


# ============ API Routes ============


@router.post("/login/start", response_model=LoginStartResponse)
async def start_account_login(
    request: LoginStartRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    开始账号登录流程（发送验证码）

    1. 用户输入账号名和手机号
    2. 系统发送验证码到手机
    3. 返回 phone_code_hash 用于后续验证
    """
    try:
        limit_key = _apply_rate_limit(
            "accounts.login.start",
            http_request,
            "Too many account login code requests. Please try again later.",
            request.account_name,
            request.phone_number,
            max_attempts=6,
            window_seconds=600,
            block_seconds=900,
        )
        result = await get_telegram_service().start_login(
            account_name=request.account_name,
            phone_number=request.phone_number,
            proxy=request.proxy,
        )
        rate_limiter.reset("accounts.login.start", limit_key)

        return LoginStartResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发送验证码失败: {str(e)}",
        )


@router.post("/login/verify", response_model=LoginVerifyResponse)
async def verify_account_login(
    request: LoginVerifyRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    验证账号登录（输入验证码和可选的2FA密码）

    1. 用户输入验证码
    2. 如果启用了2FA，还需要输入2FA密码
    3. 验证成功后，生成 session 文件
    """
    try:
        limit_key = _apply_rate_limit(
            "accounts.login.verify",
            http_request,
            "Too many account login verification attempts. Please try again later.",
            request.account_name,
            request.phone_number,
            max_attempts=8,
            window_seconds=600,
            block_seconds=900,
        )
        result = await get_telegram_service().verify_login(
            account_name=request.account_name,
            phone_number=request.phone_number,
            phone_code=request.phone_code,
            phone_code_hash=request.phone_code_hash,
            password=request.password,
            proxy=request.proxy,
        )
        rate_limiter.reset("accounts.login.verify", limit_key)

        return LoginVerifyResponse(
            success=True,
            user_id=result.get("user_id"),
            first_name=result.get("first_name"),
            username=result.get("username"),
            message="登录成功",
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录验证失败: {str(e)}",
        )


@router.post("/qr/start", response_model=QrLoginStartResponse)
async def start_qr_login(
    request: QrLoginStartRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
):
    """开始扫码登录流程"""
    try:
        limit_key = _apply_rate_limit(
            "accounts.qr.start",
            http_request,
            "Too many QR login requests. Please try again later.",
            request.account_name,
            max_attempts=8,
            window_seconds=600,
            block_seconds=900,
        )
        result = await get_telegram_service().start_qr_login(
            account_name=request.account_name, proxy=request.proxy
        )
        rate_limiter.reset("accounts.qr.start", limit_key)

        qr_image = None
        try:
            import base64
            from io import BytesIO

            import qrcode

            qr = qrcode.QRCode(version=1, box_size=8, border=2)
            qr.add_data(result["qr_uri"])
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            qr_image = "data:image/png;base64," + base64.b64encode(
                buf.getvalue()
            ).decode("utf-8")
        except Exception:
            qr_image = None

        return QrLoginStartResponse(
            login_id=result["login_id"],
            qr_uri=result["qr_uri"],
            qr_image=qr_image,
            expires_at=result["expires_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"开始扫码登录失败: {str(e)}",
        )


@router.get("/qr/status", response_model=QrLoginStatusResponse)
async def get_qr_login_status(
    login_id: str, current_user: User = Depends(get_current_user)
):
    """获取扫码登录状态"""
    try:
        result = await get_telegram_service().get_qr_login_status(login_id)
        account = result.get("account")
        if account:
            account = AccountInfo(**account)
        return QrLoginStatusResponse(
            status=result.get("status"),
            expires_at=result.get("expires_at"),
            message=result.get("message"),
            account=account,
            user_id=result.get("user_id"),
            first_name=result.get("first_name"),
            username=result.get("username"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取扫码状态失败: {str(e)}",
        )


@router.post("/qr/password", response_model=QrLoginPasswordResponse)
async def submit_qr_login_password(
    request: QrLoginPasswordRequest,
    http_request: Request,
    current_user: User = Depends(get_current_user),
):
    """提交扫码登录 2FA 密码"""
    try:
        limit_key = _apply_rate_limit(
            "accounts.qr.password",
            http_request,
            "Too many QR password attempts. Please try again later.",
            request.login_id,
            max_attempts=5,
            window_seconds=600,
            block_seconds=900,
        )
        result = await get_telegram_service().submit_qr_password(
            request.login_id, request.password
        )
        rate_limiter.reset("accounts.qr.password", limit_key)
        account = result.get("account")
        if account:
            account = AccountInfo(**account)
        return QrLoginPasswordResponse(
            success=True,
            message=result.get("message", "登录成功"),
            account=account,
            user_id=result.get("user_id"),
            first_name=result.get("first_name"),
            username=result.get("username"),
        )
    except ValueError as e:
        logger.warning("qr_password_failed login_id=%s error=%s", request.login_id, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交 2FA 密码失败: {str(e)}",
        )


@router.post("/qr/cancel", response_model=QrLoginCancelResponse)
async def cancel_qr_login(
    request: QrLoginCancelRequest, current_user: User = Depends(get_current_user)
):
    """取消扫码登录"""
    try:
        success = await get_telegram_service().cancel_qr_login(request.login_id)
        return QrLoginCancelResponse(
            success=success,
            message="已取消" if success else "登录已失效",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"取消扫码登录失败: {str(e)}",
        )


@router.get("", response_model=AccountListResponse)
def list_accounts(current_user: User = Depends(get_current_user)):
    """
    获取所有账号列表

    返回所有 session 文件对应的账号
    """
    try:
        accounts = get_telegram_service().list_accounts()

        return AccountListResponse(
            accounts=[AccountInfo(**acc) for acc in accounts], total=len(accounts)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取账号列表失败: {str(e)}",
        )


@router.post("/status/check", response_model=AccountStatusCheckResponse)
async def check_accounts_status(
    request: AccountStatusCheckRequest, current_user: User = Depends(get_current_user)
):
    """
    批量检测账号状态。

    说明：
    - 默认按当前账号列表检测；
    - 顺序检测并做轻微节流，避免刷新页面时触发请求洪峰。
    """
    service = get_telegram_service()
    try:
        if request.account_names:
            names = []
            seen = set()
            for name in request.account_names:
                normalized = (name or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                names.append(normalized)
        else:
            names = [item.get("name", "") for item in service.list_accounts()]
            names = [n for n in names if n]

        timeout_seconds = max(1.0, min(float(request.timeout_seconds or 8.0), 20.0))
        results: list[AccountStatusItem] = []
        for idx, name in enumerate(names):
            try:
                item = await service.check_account_status(
                    name, timeout_seconds=timeout_seconds
                )
            except Exception as exc:
                item = {
                    "account_name": name,
                    "ok": False,
                    "status": "error",
                    "message": str(exc) or "status check failed",
                    "code": "STATUS_CHECK_FAILED",
                    "checked_at": None,
                    "needs_relogin": False,
                }
            results.append(AccountStatusItem(**item))
            if idx < len(names) - 1:
                await asyncio.sleep(0.15)

        return AccountStatusCheckResponse(results=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"账号状态检测失败: {str(e)}",
        )


@router.get("/logs/recent", response_model=list[dict])
def get_recent_account_logs(
    limit: int = 50, current_user: User = Depends(get_current_user)
):
    from backend.services.sign_tasks import get_sign_task_service

    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    history = get_sign_task_service().get_recent_history_logs(limit=limit)
    logs: list[dict] = []
    for idx, item in enumerate(history):
        task_name = item.get("task_name", "Unknown Task")
        success = bool(item.get("success", False))
        logs.append(
            {
                "id": idx + 1,
                "account_name": item.get("account_name", ""),
                "task_name": task_name,
                "message": item.get("message")
                or ("Task succeeded" if success else "Task failed"),
                "summary": f"Task: {task_name} {'success' if success else 'failed'}",
                "bot_message": _extract_last_bot_message(item) or None,
                "success": success,
                "created_at": item.get("time", ""),
            }
        )
    return logs


@router.delete("/{account_name}", response_model=DeleteAccountResponse)
async def delete_account(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """
    删除账号（删除 session 文件）

    注意：删除后无法恢复，需要重新登录
    """
    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
        success = await get_telegram_service().delete_account(account_name)

        if success:
            return DeleteAccountResponse(
                success=True, message=f"账号 {account_name} 已删除"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账号 {account_name} 不存在",
            )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除账号失败: {str(e)}",
        )


@router.get("/{account_name}/exists")
def check_account_exists(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """检查账号是否存在"""
    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    exists = get_telegram_service().account_exists(account_name)
    return {"exists": exists, "account_name": account_name}


@router.get("/{account_name}/avatar")
async def get_account_avatar(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """获取账号 Telegram 头像（带本地缓存）"""
    import time

    from fastapi.responses import FileResponse, Response
    from backend.core.config import get_settings

    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    settings = get_settings()
    avatar_cache_dir = settings.resolve_workdir() / "avatars"
    avatar_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = avatar_cache_dir / f"{account_name}.jpg"
    no_avatar_marker = avatar_cache_dir / f"{account_name}.no_avatar"

    # 如果已标记为无头像（7天内），直接返回 404
    if no_avatar_marker.exists():
        age = time.time() - no_avatar_marker.stat().st_mtime
        if age < 604800:
            raise HTTPException(status_code=404, detail="No avatar available")
        else:
            no_avatar_marker.unlink(missing_ok=True)

    # 如果缓存存在且不超过 7 天，直接返回
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 604800:
            return FileResponse(cache_file, media_type="image/jpeg")

    # 尝试下载头像
    try:
        avatar_bytes = await get_telegram_service().download_account_avatar(account_name)
        if avatar_bytes:
            cache_file.write_bytes(avatar_bytes)
            no_avatar_marker.unlink(missing_ok=True)
            return Response(content=avatar_bytes, media_type="image/jpeg")
        else:
            no_avatar_marker.write_text("")
    except Exception:
        if cache_file.exists():
            return FileResponse(cache_file, media_type="image/jpeg")
        no_avatar_marker.write_text("")

    raise HTTPException(status_code=404, detail="No avatar available")


@router.patch("/{account_name}", response_model=AccountUpdateResponse)
async def update_account(
    account_name: str,
    request: AccountUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新账号备注/代理（不影响登录状态）
    """
    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
        if request.new_account_name:
            validate_storage_name(request.new_account_name, field_name="new_account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    service = get_telegram_service()
    accounts = service.list_accounts(force_refresh=True)
    current_account = next(
        (
            acc
            for acc in accounts
            if str(acc.get("name") or "").strip().lower() == account_name.strip().lower()
        ),
        None,
    )
    if not current_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
        )

    try:
        from backend.utils.tg_session import set_account_profile

        actual_account_name = str(current_account.get("name") or account_name).strip()
        target_account_name = (
            request.new_account_name.strip()
            if isinstance(request.new_account_name, str) and request.new_account_name.strip()
            else actual_account_name
        )
        renamed = target_account_name != actual_account_name
        if renamed:
            target_account_name = await service.rename_account(
                actual_account_name,
                target_account_name,
            )

        set_account_profile(
            target_account_name,
            remark=request.remark,
            proxy=request.proxy,
        )

        if renamed:
            from backend.scheduler import sync_jobs

            await sync_jobs()

        try:
            from backend.services.keyword_monitor import get_keyword_monitor_service

            await get_keyword_monitor_service().restart_from_tasks()
        except Exception:
            pass

        updated = next(
            (
                acc
                for acc in service.list_accounts(force_refresh=True)
                if acc.get("name") == target_account_name
            ),
            None,
        )
        if not updated:
            raise ValueError("账号信息更新后未找到对应账号")

        return AccountUpdateResponse(
            success=True,
            message="Account updated",
            account=AccountInfo(**updated),
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新账号信息失败: {str(e)}",
        )

class AccountLogItem(BaseModel):
    """账号日志项"""

    id: int
    account_name: str
    task_name: str
    message: str
    summary: Optional[str] = None
    bot_message: Optional[str] = None
    success: bool
    created_at: str


def _extract_last_bot_message(item: dict) -> str:
    stored = str(item.get("last_target_message") or "").strip()
    if stored:
        return stored
    return extract_last_target_message(item.get("flow_logs"))


class ClearAccountLogsResponse(BaseModel):
    """清理账号日志响应"""

    success: bool
    cleared: int
    message: str
    code: Optional[str] = None


@router.post("/logs/clear", response_model=ClearAccountLogsResponse)
def clear_recent_account_logs(current_user: User = Depends(get_current_user)):
    """清理全部最近任务执行日志"""
    try:
        from backend.services.sign_tasks import get_sign_task_service

        result = get_sign_task_service().clear_all_history_logs()
        return ClearAccountLogsResponse(
            success=True,
            cleared=result.get("removed_entries", 0),
            message="All logs cleared",
            code="LOGS_CLEARED",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLEAR_LOGS_FAILED",
        )


@router.get("/{account_name}/logs", response_model=list[AccountLogItem])
def get_account_logs(
    account_name: str, limit: int = 100, current_user: User = Depends(get_current_user)
):
    """获取账号的任务执行历史日志"""
    from backend.services.sign_tasks import get_sign_task_service

    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    history = get_sign_task_service().get_account_history_logs(account_name)

    logs = []
    for i, item in enumerate(history[:limit]):
        logs.append(
            AccountLogItem(
                id=i + 1,
                account_name=account_name,
                task_name=item.get("task_name", "未知任务"),
                message=item.get("message")
                or ("执行成功" if item.get("success") else "执行失败"),
                success=item.get("success", False),
                created_at=item.get("time", ""),
            )
        )

    for idx, item in enumerate(history[:limit]):
        if idx >= len(logs):
            break
        task_name = logs[idx].task_name or "Unknown Task"
        success = bool(logs[idx].success)
        logs[idx].summary = f"Task: {task_name} {'success' if success else 'failed'}"
        logs[idx].bot_message = _extract_last_bot_message(item) or None

    return logs


@router.post("/{account_name}/logs/clear", response_model=ClearAccountLogsResponse)
def clear_account_logs(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """清理账号的历史日志"""
    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not get_telegram_service().account_exists(account_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ACCOUNT_NOT_FOUND",
        )
    try:
        from backend.services.sign_tasks import get_sign_task_service

        result = get_sign_task_service().clear_account_history_logs(account_name)
        return ClearAccountLogsResponse(
            success=True,
            cleared=result.get("removed_entries", 0),
            message="Logs cleared",
            code="LOGS_CLEARED",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CLEAR_LOGS_FAILED",
        )


@router.get("/{account_name}/logs/export")
def export_account_logs(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """导出账号日志为 txt 文件"""
    import re
    from fastapi.responses import Response

    from backend.services.sign_tasks import get_sign_task_service

    try:
        account_name = validate_storage_name(account_name, field_name="account_name")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    history = get_sign_task_service().get_account_history_logs(account_name)

    content = f"Account Logs for: {account_name}\n"
    content += "=" * 40 + "\n\n"

    for item in history:
        time_str = item.get("time", "").replace("T", " ")[:19]
        status = "SUCCESS" if item.get("success") else "FAILED"
        content += f"[{time_str}] Task: {item.get('task_name')} | Status: {status}\n"
        if item.get("message"):
            content += f"Message: {item.get('message')}\n"
        content += "-" * 20 + "\n"

    safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", account_name) or "account"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_logs.txt"'
        },
    )
