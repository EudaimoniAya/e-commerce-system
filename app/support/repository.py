"""support 域仓储层：SupportConversation / SupportMessage CRUD 与分页查询。

跨域纪律：仅操作 support 域 ORM，不 import catalog / ordering 模型或仓储。
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.support.models import SupportConversation, SupportMessage


class ConversationRepository:
    """会话仓储（support_conversations 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, conversation: SupportConversation) -> None:
        """持久化新会话（service 须先构造 ORM 实例）。"""
        self._session.add(conversation)

    async def get_by_id(
        self,
        conversation_id: uuid.UUID,
    ) -> SupportConversation | None:
        """按主键查询会话。"""
        return await self._session.get(SupportConversation, conversation_id)

    async def get_by_shop_and_buyer(
        self,
        shop_id: uuid.UUID,
        buyer_user_id: uuid.UUID,
    ) -> SupportConversation | None:
        """按 ``(shop_id, buyer_user_id)`` 查唯一会话（lazy create 前定位）。"""
        stmt = select(SupportConversation).where(
            SupportConversation.shop_id == str(shop_id),
            SupportConversation.buyer_user_id == str(buyer_user_id),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_shop(
        self,
        shop_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[SupportConversation], int]:
        """分页返回店铺全部会话（updated_at DESC，供 inbox）+ total 计数。"""
        base = select(SupportConversation).where(
            SupportConversation.shop_id == str(shop_id)
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())

        result = await self._session.execute(
            base.order_by(SupportConversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows: Sequence[SupportConversation] = result.scalars().all()
        return list(rows), total


class MessageRepository:
    """消息仓储（support_messages 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, message: SupportMessage) -> None:
        """持久化新消息（service 须先构造 ORM 实例）。"""
        self._session.add(message)

    async def list_by_conversation(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[SupportMessage], int]:
        """分页返回会话内消息（created_at ASC，供双方历史）+ total 计数。"""
        base = select(SupportMessage).where(
            SupportMessage.conversation_id == str(conversation_id)
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())

        result = await self._session.execute(
            base.order_by(SupportMessage.created_at.asc()).limit(limit).offset(offset)
        )
        rows: Sequence[SupportMessage] = result.scalars().all()
        return list(rows), total
