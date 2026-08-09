"""support 域业务逻辑：买家会话/发消息、店主 inbox/回复、product ref 校验。

跨域纪律：商品与店铺校验仅经 ``catalog.service``（ProductService / ShopService）
与 schema（``ShopContext``），禁止 import catalog / ordering ORM 或 repository。
"""

import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.product_service import ProductService
from app.catalog.shop_service import ShopService
from app.support.models import SupportConversation, SupportMessage
from app.support.repository import ConversationRepository, MessageRepository
from app.support.schemas import (
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    PaginatedConversations,
    PaginatedMessages,
)

_SHOP_NOT_FOUND_MSG = "Shop not found"
_CONVERSATION_NOT_FOUND_MSG = "Conversation not found"
_SELF_SUPPORT_MSG = "Shop owner cannot support their own shop"
_SHOP_CLOSED_MSG = "Shop is closed"
_EMPTY_MESSAGE_MSG = "body and message_refs cannot both be empty"
_ORDER_REF_MSG = "order ref is not supported yet"
_TOO_MANY_REFS_MSG = "message_refs must contain at most 10 distinct items"
_PREVIEW_MAX = 200


def _to_conversation_response(
    conversation: SupportConversation,
) -> ConversationResponse:
    """ORM SupportConversation → ConversationResponse。"""
    return ConversationResponse(
        id=str(conversation.id),
        shop_id=str(conversation.shop_id),
        buyer_user_id=str(conversation.buyer_user_id),
        handler_mode=conversation.handler_mode,
        last_message_preview=conversation.last_message_preview,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _to_message_response(message: SupportMessage) -> MessageResponse:
    """ORM SupportMessage → MessageResponse（refs 仅含 ref_type/ref_id）。"""
    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        sender_role=message.sender_role,
        author_role=message.author_role,
        body=message.body,
        message_refs=message.message_refs,
        created_at=message.created_at,
    )


class SupportService:
    """support 域编排服务（注入 catalog ShopService + ProductService 做店铺/product ref 校验）。"""

    def __init__(
        self,
        session: AsyncSession,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        shop_service: ShopService,
        product_service: ProductService,
    ) -> None:
        self._session = session
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._shops = shop_service
        self._products = product_service

    # ── 本店解析（店主路径）──────────────────────────────────

    async def _get_current_shop_id(self, user_id: uuid.UUID) -> uuid.UUID:
        """解析当前用户店铺 id（经 catalog `ShopService.get_my_shop`，404 语义一致）。

        店主路径不再跨域 `Depends(get_current_shop)`——本域 service 经 catalog service 解析；
        跨域上下文由业务方法内部自解析，router 一步调用（Phase D）。
        """
        shop = await self._shops.get_my_shop(user_id)
        return uuid.UUID(str(shop.id))

    # ── 买家路径 ──────────────────────────────────────────────

    async def get_buyer_conversation(
        self,
        shop_id: uuid.UUID,
        buyer_user_id: uuid.UUID,
    ) -> ConversationResponse:
        """买家查询会话：无会话 404；店主走买家路径 403；shop 不存在 404。"""
        shop = await self._shops.get_shop_context(shop_id)
        self._ensure_not_owner(buyer_user_id, shop.owner_user_id)

        conversation = await self._conversation_repo.get_by_shop_and_buyer(
            shop_id, buyer_user_id
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_CONVERSATION_NOT_FOUND_MSG,
            )
        return _to_conversation_response(conversation)

    async def list_buyer_messages(
        self,
        shop_id: uuid.UUID,
        buyer_user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedMessages:
        """买家拉取会话消息（created_at ASC）：无会话 404。"""
        shop = await self._shops.get_shop_context(shop_id)
        self._ensure_not_owner(buyer_user_id, shop.owner_user_id)

        conversation = await self._conversation_repo.get_by_shop_and_buyer(
            shop_id, buyer_user_id
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_CONVERSATION_NOT_FOUND_MSG,
            )
        return await self._list_messages(conversation.id, limit=limit, offset=offset)

    async def send_buyer_message(
        self,
        shop_id: uuid.UUID,
        buyer_user_id: uuid.UUID,
        data: MessageCreate,
    ) -> MessageResponse:
        """买家发消息：lazy create 会话（单事务）；closed 店任何 POST 422。"""
        shop = await self._shops.get_shop_context(shop_id)
        self._ensure_not_owner(buyer_user_id, shop.owner_user_id)
        if shop.status == "closed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_SHOP_CLOSED_MSG,
            )

        refs = await self._validate_message(data, shop_id)

        conversation = await self._conversation_repo.get_by_shop_and_buyer(
            shop_id, buyer_user_id
        )
        if conversation is None:
            conversation = SupportConversation(
                id=uuid.uuid4(),
                shop_id=shop_id,
                buyer_user_id=buyer_user_id,
                handler_mode="human",
            )
            await self._conversation_repo.save(conversation)

        message = await self._persist_message(
            conversation,
            sender_role="buyer",
            body=data.body,
            refs=refs,
        )
        return _to_message_response(message)

    # ── 店主路径 ──────────────────────────────────────────────

    async def list_inbox(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedConversations:
        """本店会话分页列表（updated_at DESC，含 last_message_preview）。

        店主身份经 `_get_current_shop_id` 内部解析（router 不再两步调用）。
        """
        shop_id = await self._get_current_shop_id(user_id)
        conversations, total = await self._conversation_repo.list_by_shop(
            shop_id, limit=limit, offset=offset
        )
        return PaginatedConversations(
            items=[_to_conversation_response(c) for c in conversations],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_inbox_conversation(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationResponse:
        """店主查看会话详情：非本店会话 404。"""
        shop_id = await self._get_current_shop_id(user_id)
        conversation = await self._get_shop_conversation(shop_id, conversation_id)
        return _to_conversation_response(conversation)

    async def list_inbox_messages(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedMessages:
        """店主拉取会话消息（created_at ASC）：非本店会话 404。"""
        shop_id = await self._get_current_shop_id(user_id)
        conversation = await self._get_shop_conversation(shop_id, conversation_id)
        return await self._list_messages(conversation.id, limit=limit, offset=offset)

    async def send_shop_message(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        data: MessageCreate,
    ) -> MessageResponse:
        """店主回复：closed 店铺仍允许（售后收尾）。"""
        shop_id = await self._get_current_shop_id(user_id)
        conversation = await self._get_shop_conversation(shop_id, conversation_id)
        refs = await self._validate_message(data, uuid.UUID(str(conversation.shop_id)))
        message = await self._persist_message(
            conversation,
            sender_role="shop",
            body=data.body,
            refs=refs,
        )
        return _to_message_response(message)

    # ── 私有内核 ──────────────────────────────────────────────

    def _ensure_not_owner(self, buyer_user_id: uuid.UUID, owner_user_id: str) -> None:
        """买家 == 店主（禁自购延伸）→ 403。"""
        if str(buyer_user_id) == owner_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_SELF_SUPPORT_MSG,
            )

    async def _get_shop_conversation(
        self,
        shop_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> SupportConversation:
        """按 ID 定位会话并校验属于本店；不存在或非本店 → 404（不暴露存在性）。"""
        conversation = await self._conversation_repo.get_by_id(conversation_id)
        if conversation is None or str(conversation.shop_id) != str(shop_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_CONVERSATION_NOT_FOUND_MSG,
            )
        return conversation

    async def _validate_message(
        self,
        data: MessageCreate,
        shop_id: uuid.UUID,
    ) -> list[dict[str, str]]:
        """校验 body/refs 规则，返回去重后的 refs（响应仅存 ref_type/ref_id）。

        规则：body 与 refs 至少一项非空；order ref 422；去重后 ≤10；product ref 经
        catalog service 校验归属 shop_id（未上架允许）。
        """
        body = data.body or ""
        refs = data.message_refs or []
        if not body and not refs:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_EMPTY_MESSAGE_MSG,
            )

        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for ref in refs:
            key = (ref.ref_type, ref.ref_id)
            if key not in seen:
                seen.add(key)
                deduped.append({"ref_type": ref.ref_type, "ref_id": ref.ref_id})

        if len(deduped) > 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_TOO_MANY_REFS_MSG,
            )

        product_ids: list[uuid.UUID] = []
        for ref in deduped:
            if ref["ref_type"] == "order":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=_ORDER_REF_MSG,
                )
            product_ids.append(uuid.UUID(ref["ref_id"]))

        if product_ids:
            await self._products.validate_product_refs_for_shop(shop_id, product_ids)
        return deduped

    async def _persist_message(
        self,
        conversation: SupportConversation,
        *,
        sender_role: Literal["buyer", "shop"],
        body: str | None,
        refs: list[dict[str, str]],
    ) -> SupportMessage:
        """单事务写入消息 + bump 会话 preview/updated_at。"""
        message = SupportMessage(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            sender_role=sender_role,
            author_role="human",
            body=body,
            message_refs=refs or None,
        )
        await self._message_repo.save(message)
        # body 截断前 200 字符；ref-only 消息 preview 为空字符串
        conversation.last_message_preview = (body or "")[:_PREVIEW_MAX]
        # updated_at 由 ORM onupdate=func.now() 在 commit 时 bump
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def _list_messages(
        self,
        conversation_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> PaginatedMessages:
        """分页查询会话内消息（created_at ASC）。"""
        messages, total = await self._message_repo.list_by_conversation(
            conversation_id, limit=limit, offset=offset
        )
        return PaginatedMessages(
            items=[_to_message_response(m) for m in messages],
            total=total,
            limit=limit,
            offset=offset,
        )
