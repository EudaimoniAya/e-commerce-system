"""support 域 FastAPI 依赖。"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.deps import get_shop_service
from app.catalog.service import ShopService
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
    conversation_repo: ConversationRepository = Depends(
        get_conversation_repository
    ),
    message_repo: MessageRepository = Depends(get_message_repository),
    catalog_service: ShopService = Depends(get_shop_service),
) -> SupportService:
    """注入 support 编排服务（共享同一 DB 事务；跨域依赖 catalog service）。"""
    return SupportService(session, conversation_repo, message_repo, catalog_service)
