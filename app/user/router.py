"""user 域 HTTP 路由（登录、当前用户）。

.. note::
    ``POST /auth/register`` 与 ``POST /auth/sms/verify`` 已移除（见 design.md Decision 2）。
    SMS OTP 端点（``/auth/sms/send``、``/auth/sms/register``、``/auth/sms/login``）
    与 ``PATCH /users/me`` 将在 §5.3 实现。
"""

from fastapi import APIRouter, Depends

from app.user.deps import get_current_user, get_user_service
from app.user.schemas import LoginRequest, TokenResponse, UserResponse
from app.user.service import UserService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """手机号 + 密码登录并返回 access token。"""
    return await service.login(body)


@router.get("/users/me", response_model=UserResponse)
async def read_current_user(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """返回当前认证用户资料。"""
    return current_user
