"""user 域 HTTP 路由（注册、登录、当前用户）。"""

from fastapi import APIRouter, Depends, status

from app.user.deps import get_current_user, get_user_service
from app.user.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.user.service import UserService

router = APIRouter(tags=["auth"])


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """注册新用户并返回 access token。"""
    return await service.register(body)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    """JSON 登录并返回 access token。"""
    return await service.login(body)


@router.get("/users/me", response_model=UserResponse)
async def read_current_user(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """返回当前认证用户资料。"""
    return current_user
