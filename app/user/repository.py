"""user 域持久化层（仅接收 password_hash，不见明文）。"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.models import User

_UNSET: Any = object()  # sentinel：区分"未传"与"显式传 None"


class UserRepository:
    """users 表 CRUD。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """按主键查询用户。"""
        return await self._session.get(User, str(user_id))

    async def get_by_email(self, email: str) -> User | None:
        """按邮箱查询用户。"""
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        """按规范化手机号查询用户。"""
        result = await self._session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        phone: str,
        password_hash: str,
        nickname: str,
        email: str | None = None,
    ) -> User:
        """创建用户并提交事务。"""
        user = User(
            id=str(user_id),
            phone=phone,
            email=email,
            password_hash=password_hash,
            nickname=nickname,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_profile(
        self,
        user: User,
        *,
        email: Any = _UNSET,
        nickname: Any = _UNSET,
    ) -> User:
        """更新用户资料字段（email / nickname）并提交。

        ``email`` 显式传 ``None`` 表示清空 email。
        未传的字段保持不变。
        """
        if email is not _UNSET:
            user.email = email
        if nickname is not _UNSET:
            user.nickname = nickname
        await self._session.commit()
        await self._session.refresh(user)
        return user
