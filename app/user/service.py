"""user 域业务逻辑（注册、登录、密码哈希）。"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from pwdlib import PasswordHash

from app.infra.auth import create_access_token
from app.user.repository import UserRepository
from app.user.schemas import (
    LoginRequest,
    TokenResponse,
    UserResponse,
    UserSummary,
)

_hasher = PasswordHash.recommended()

# 登录失败统一文案，不区分手机号是否存在
_INVALID_CREDENTIALS_MSG = "Invalid phone or password"


def _default_nickname() -> str:
    """未提供昵称时生成默认昵称（用户_ + 毫秒级时间戳）。"""
    now = datetime.now()
    return f"用户_{now.strftime('%Y%m%d%H%M%S')}{now.microsecond // 1000:03d}"


def _to_user_response(user) -> UserResponse:
    """ORM 用户转对外 DTO。

    .. note::
        迁移过渡期间旧 email 式 ORM 行（尚无 phone 列）可能触发 IntegrityError；
        §3（migration 008）后 ``user.phone`` 一定存在且非空。
    """
    return UserResponse(
        id=str(user.id),
        phone=getattr(user, "phone", ""),
        email=user.email,
        nickname=user.nickname,
        created_at=user.created_at,
    )


def _build_token_response(user) -> TokenResponse:
    """签发 token 并组装响应。"""
    user_uuid = uuid.UUID(str(user.id))
    access_token, expires_in = create_access_token(user_uuid)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_to_user_response(user),
    )


class UserService:
    """用户注册与登录服务。"""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    # register 已随 email 注册路径移除；SMS register/login 见 §5.2

    async def get_user_summary(self, user_id: uuid.UUID | str) -> UserSummary:
        """查询用户摘要（跨域只读）。"""
        user = await self._repository.get_by_id(uuid.UUID(str(user_id)))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="User account is disabled",
            )
        return UserSummary(id=str(user.id), nickname=user.nickname)

    async def login(self, data: LoginRequest) -> TokenResponse:
        """通过手机号 + 密码校验凭据并返回 access token。"""
        # 迁移过渡：8 位 UUID 字符串长度 < 11，可区分 email（含 @）与 phone 查法
        user = await self._repository.get_by_phone(data.identifier)
        if user is None or not _hasher.verify(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_INVALID_CREDENTIALS_MSG,
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return _build_token_response(user)
