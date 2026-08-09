"""user 域 HTTP 路由（SMS 认证、密码登录、当前用户）。"""

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.infra.auth import get_current_user_id
from app.user.deps import get_user_service
from app.user.schemas import (
    LoginRequest,
    SmsLoginRequest,
    SmsRegisterRequest,
    SmsSendRequest,
    TokenResponse,
    UserProfileUpdateRequest,
    UserResponse,
)
from app.user.service import UserService

router = APIRouter(tags=["auth"])


@router.post("/auth/sms/send", status_code=status.HTTP_200_OK)
async def send_sms(
    body: SmsSendRequest,
    service: UserService = Depends(get_user_service),
) -> Response:
    """发送 SMS OTP（响应不区分用户是否存在）。"""
    await service.send_sms(body)
    return Response(status_code=status.HTTP_200_OK)


@router.post(
    "/auth/sms/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_via_sms(
    body: SmsRegisterRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """SMS OTP 注册新用户。"""
    return await service.register_via_sms(body)


@router.post("/auth/sms/login", response_model=TokenResponse)
async def login_via_sms(
    body: SmsLoginRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """SMS OTP 登录已有用户。"""
    return await service.login_via_sms(body)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """手机号 + 密码登录并返回 access token。"""
    return await service.login(body)


@router.get("/users/me", response_model=UserResponse)
async def read_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """返回当前认证用户资料（fetch/avatar/映射由 service 产出）。"""
    return await service.get_user_response(user_id)


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user(
    body: UserProfileUpdateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """更新当前用户资料（email / nickname）。"""
    return await service.update_profile(user_id, body)
