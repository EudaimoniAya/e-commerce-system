"""support 域 HTTP 路由。

- 买家路径：``/support/shops/{shop_id}/*``（Bearer JWT，``get_current_user_id``）
- 店主路径：``/support/inbox/*``（``catalog.deps.get_current_shop``，单人店 MVP）
"""

import uuid

from fastapi import APIRouter, Depends, status

from app.catalog.deps import get_current_shop
from app.catalog.models import Shop
from app.infra.auth import get_current_user_id
from app.infra.pagination.deps import get_pagination_params
from app.infra.pagination.schemas import PaginationParams
from app.support.deps import get_support_service
from app.support.schemas import (
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    PaginatedConversations,
    PaginatedMessages,
)
from app.support.service import SupportService

router = APIRouter()


# ── 买家路径 ──────────────────────────────────────────────


@router.get(
    "/support/shops/{shop_id}/conversation",
    response_model=ConversationResponse,
    tags=["support"],
)
async def get_buyer_conversation(
    shop_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SupportService = Depends(get_support_service),
) -> ConversationResponse:
    """买家查询会话：有 200，无 / shop 不存在 / 店主自访 4xx。"""
    return await service.get_buyer_conversation(shop_id, user_id)


@router.post(
    "/support/shops/{shop_id}/conversation/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["support"],
)
async def post_buyer_message(
    shop_id: uuid.UUID,
    body: MessageCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SupportService = Depends(get_support_service),
) -> MessageResponse:
    """买家发消息：lazy create 会话；closed 店 / 校验失败 4xx。"""
    return await service.send_buyer_message(shop_id, user_id, body)


@router.get(
    "/support/shops/{shop_id}/conversation/messages",
    response_model=PaginatedMessages,
    tags=["support"],
)
async def list_buyer_messages(
    shop_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    service: SupportService = Depends(get_support_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> PaginatedMessages:
    """买家拉取会话消息（created_at ASC）。"""
    return await service.list_buyer_messages(
        shop_id,
        user_id,
        limit=params.limit,
        offset=params.offset,
    )


# ── 店主路径 ──────────────────────────────────────────────


@router.get(
    "/support/inbox",
    response_model=PaginatedConversations,
    tags=["support"],
)
async def list_inbox(
    shop: Shop = Depends(get_current_shop),
    service: SupportService = Depends(get_support_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> PaginatedConversations:
    """本店会话分页列表（updated_at DESC，含 last_message_preview）。"""
    return await service.list_inbox(
        uuid.UUID(str(shop.id)),
        limit=params.limit,
        offset=params.offset,
    )


@router.get(
    "/support/inbox/{conversation_id}",
    response_model=ConversationResponse,
    tags=["support"],
)
async def get_inbox_conversation(
    conversation_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    service: SupportService = Depends(get_support_service),
) -> ConversationResponse:
    """店主查看会话详情：非本店会话 404。"""
    return await service.get_inbox_conversation(
        uuid.UUID(str(shop.id)), conversation_id
    )


@router.get(
    "/support/inbox/{conversation_id}/messages",
    response_model=PaginatedMessages,
    tags=["support"],
)
async def list_inbox_messages(
    conversation_id: uuid.UUID,
    shop: Shop = Depends(get_current_shop),
    service: SupportService = Depends(get_support_service),
    params: PaginationParams = Depends(get_pagination_params),
) -> PaginatedMessages:
    """店主拉取会话消息（created_at ASC）。"""
    return await service.list_inbox_messages(
        uuid.UUID(str(shop.id)),
        conversation_id,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/support/inbox/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["support"],
)
async def post_shop_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    shop: Shop = Depends(get_current_shop),
    service: SupportService = Depends(get_support_service),
) -> MessageResponse:
    """店主回复：closed 店铺仍允许（售后收尾）。"""
    return await service.send_shop_message(
        uuid.UUID(str(shop.id)), conversation_id, body
    )
