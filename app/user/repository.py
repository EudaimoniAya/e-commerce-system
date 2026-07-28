"""user 域持久化层（仅接收 password_hash，不见明文）。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.models import User


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
        email: str,
        password_hash: str,
        nickname: str,
    ) -> User:
        """创建用户并提交事务。"""
        user = User(
            id=str(user_id),
            email=email,
            password_hash=password_hash,
            nickname=nickname,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user
