"""user 域 FastAPI 依赖。"""

import uuid

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user_id
from app.infra.config import get_settings
from app.infra.database import get_db
from app.infra.redis import get_redis
from app.media.deps import get_media_service
from app.media.service import MediaService
from app.user.models import User
from app.user.repository import UserRepository
from app.user.service import UserService
from app.user.sms_service import SmsOtpService


def get_user_repository(
    session: AsyncSession = Depends(get_db),
) -> UserRepository:
    """注入 user 仓储。"""
    return UserRepository(session)


def get_sms_service(
    redis: aioredis.Redis = Depends(get_redis),
) -> SmsOtpService:
    """注入 SMS OTP 服务（含 Redis 客户端与配置）。"""
    return SmsOtpService(redis, get_settings())


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
    sms: SmsOtpService = Depends(get_sms_service),
    media_service: MediaService = Depends(get_media_service),
) -> UserService:
    """注入 user 服务。"""
    return UserService(repository, sms, media_service)


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


async def get_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    repository: UserRepository = Depends(get_user_repository),
) -> User:
    """解析 JWT 并查库返回当前用户实体；用户不存在 404。

    纯读解析（design Decision 4b）：本域仓储直读 + 404，无副作用；
    返 User ORM 供本域 router 消费（推翻 Phase B service 内自解析）。
    """
    user = await repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
