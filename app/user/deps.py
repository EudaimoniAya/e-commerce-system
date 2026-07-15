"""user 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user_id
from app.infra.database import get_db
from app.user.repository import UserRepository
from app.user.schemas import UserResponse
from app.user.service import UserService, _to_user_response


def get_user_repository(
    session: AsyncSession = Depends(get_db),
) -> UserRepository:
    """注入 user 仓储。"""
    return UserRepository(session)


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    """注入 user 服务。"""
    return UserService(repository)


async def get_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    repository: UserRepository = Depends(get_user_repository),
) -> UserResponse:
    """解析 JWT 并查库返回当前用户；用户不存在时 401。"""
    user = await repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _to_user_response(user)


async def require_admin(
    user_id: uuid.UUID = Depends(get_current_user_id),
    repository: UserRepository = Depends(get_user_repository),
) -> uuid.UUID:
    """解析 JWT 并查库验证管理员；非 admin → 403，用户不存在 → 401。"""
    user = await repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user_id
