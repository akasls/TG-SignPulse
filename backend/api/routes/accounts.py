"""
账号管理 API 路由（重构版）
基于原项目逻辑，使用手机号登录
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.auth import get_current_user
from backend.models.user import User
from backend.services.telegram import get_telegram_service

router = APIRouter()


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


class AccountListResponse(BaseModel):
    """账号列表响应"""

    accounts: list[AccountInfo]
    total: int


class DeleteAccountResponse(BaseModel):
    """删除账号响应"""

    success: bool
    message: str


class AccountUpdateRequest(BaseModel):
    """更新账号备注/代理"""

    remark: Optional[str] = None
    proxy: Optional[str] = None


class AccountUpdateResponse(BaseModel):
    """更新账号响应"""

    success: bool
    message: str
    account: Optional[AccountInfo] = None


# ============ API Routes ============


@router.post("/login/start", response_model=LoginStartResponse)
async def start_account_login(
    request: LoginStartRequest, current_user: User = Depends(get_current_user)
):
    """
    开始账号登录流程（发送验证码）

    1. 用户输入账号名和手机号
    2. 系统发送验证码到手机
    3. 返回 phone_code_hash 用于后续验证
    """
    try:
        result = await get_telegram_service().start_login(
            account_name=request.account_name,
            phone_number=request.phone_number,
            proxy=request.proxy,
        )

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
    request: LoginVerifyRequest, current_user: User = Depends(get_current_user)
):
    """
    验证账号登录（输入验证码和可选的2FA密码）

    1. 用户输入验证码
    2. 如果启用了2FA，还需要输入2FA密码
    3. 验证成功后，生成 session 文件
    """
    try:
        result = await get_telegram_service().verify_login(
            account_name=request.account_name,
            phone_number=request.phone_number,
            phone_code=request.phone_code,
            phone_code_hash=request.phone_code_hash,
            password=request.password,
            proxy=request.proxy,
        )

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
    request: QrLoginStartRequest, current_user: User = Depends(get_current_user)
):
    """开始扫码登录流程"""
    try:
        result = await get_telegram_service().start_qr_login(
            account_name=request.account_name, proxy=request.proxy
        )

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


@router.delete("/{account_name}", response_model=DeleteAccountResponse)
async def delete_account(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """
    删除账号（删除 session 文件）

    注意：删除后无法恢复，需要重新登录
    """
    try:
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
    exists = get_telegram_service().account_exists(account_name)
    return {"exists": exists, "account_name": account_name}


@router.patch("/{account_name}", response_model=AccountUpdateResponse)
def update_account(
    account_name: str,
    request: AccountUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新账号备注/代理（不影响登录状态）
    """
    if not get_telegram_service().account_exists(account_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"账号 {account_name} 不存在",
        )
    try:
        from backend.utils.tg_session import set_account_profile

        set_account_profile(
            account_name,
            remark=request.remark,
            proxy=request.proxy,
        )

        # 刷新缓存并返回更新后的账号信息
        service = get_telegram_service()
        updated = None
        try:
            accounts = service.list_accounts(force_refresh=True)
            updated = next(
                (acc for acc in accounts if acc.get("name") == account_name), None
            )
        except Exception:
            updated = None

        if not updated:
            raise ValueError("账号信息更新后未找到对应账号")

        return AccountUpdateResponse(
            success=True,
            message="账号信息已更新",
            account=AccountInfo(**updated),
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
    success: bool
    created_at: str


@router.get("/{account_name}/logs", response_model=list[AccountLogItem])
def get_account_logs(
    account_name: str, limit: int = 100, current_user: User = Depends(get_current_user)
):
    """获取账号的任务执行历史日志"""
    from backend.services.sign_tasks import get_sign_task_service

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

    return logs


@router.get("/{account_name}/logs/export")
def export_account_logs(
    account_name: str, current_user: User = Depends(get_current_user)
):
    """导出账号日志为 txt 文件"""
    from fastapi.responses import Response

    from backend.services.sign_tasks import get_sign_task_service

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

    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=logs_{account_name}.txt"
        },
    )
