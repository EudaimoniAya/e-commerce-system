"""support 域 FastAPI 依赖。"""

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.deps import get_product_service, get_shop_service
from app.catalog.product_service import ProductService
from app.catalog.schemas import ShopContext
from app.catalog.shop_service import ShopService
from app.infra.auth import get_current_user_id
from app.infra.database import get_db
from app.support.repository import ConversationRepository, MessageRepository
from app.support.service import SupportService


def get_conversation_repository(
    session: AsyncSession = Depends(get_db),
) -> ConversationRepository:
    """注入会话仓储。"""
    return ConversationRepository(session)


def get_message_repository(
    session: AsyncSession = Depends(get_db),
) -> MessageRepository:
    """注入消息仓储。"""
    return MessageRepository(session)


def get_support_service(
    session: AsyncSession = Depends(get_db),
    conversation_repo: ConversationRepository = Depends(get_conversation_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    shop_service: ShopService = Depends(get_shop_service),
    product_service: ProductService = Depends(get_product_service),
) -> SupportService:
    """注入 support 编排服务（共享同一 DB 事务；跨域依赖 catalog ShopService + ProductService）。"""
    return SupportService(
        session,
        conversation_repo,
        message_repo,
        shop_service,
        product_service,
    )


async def get_current_support_shop(
    user_id: uuid.UUID = Depends(get_current_user_id),
    shop_service: ShopService = Depends(get_shop_service),
) -> ShopContext:
    """解析当前用户的店铺上下文（跨域解析 catalog shop）。

    只转发 `ShopService.get_my_shop_context`（返 ShopContext schema，不建 schema，
    design Decision 4b 跨域解析 + 4c deps 无副作用）。
    """
    return await shop_service.get_my_shop_context(user_id)
