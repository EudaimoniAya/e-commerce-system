"""support 域请求/响应 DTO。

对齐 spec：
- ``MessageCreate``：``{body?, message_refs?}``；body ≤ 2000；refs 去重后 ≤ 10（service 校验）。
- 响应 refs 仅含 ``{ref_type, ref_id}``，不 enrich 商品详情。
- 分页 envelope 复用 ``app.infra.pagination`` 的 ``Paginated[T]``。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.infra.pagination.schemas import Paginated


class MessageRef(BaseModel):
    """消息引用项：MVP 仅接受 ``product``；``order`` 由 service 422 拒绝。"""

    ref_type: Literal["product", "order"]
    ref_id: str

    @field_validator("ref_id")
    @classmethod
    def validate_ref_id(cls, value: str) -> str:
        """校验 ref_id 为合法 UUID，避免 service 层 ``uuid.UUID`` 抛 500。"""
        uuid.UUID(value)
        return value


class MessageCreate(BaseModel):
    """发消息请求体：body 与 message_refs 至少一项非空（service 校验）。"""

    body: str | None = Field(default=None, max_length=2000)
    message_refs: list[MessageRef] | None = None


class HandlerModeUpdate(BaseModel):
    """PATCH 会话模式请求体：仅 ``ai`` | ``human``。"""

    handler_mode: Literal["ai", "human"]


class ConversationResponse(BaseModel):
    """对外会话资料（买家 GET / inbox 详情 / inbox 列表项共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    shop_id: str
    buyer_user_id: str
    handler_mode: str
    last_message_preview: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """对外消息资料（买卖家发消息 / 消息列表项共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    sender_role: str
    author_role: str
    body: str | None
    message_refs: list[MessageRef] | None
    created_at: datetime


class PaginatedConversations(Paginated[ConversationResponse]):
    """分页会话列表（inbox）。"""

    model_config = ConfigDict(title="PaginatedConversations")


class PaginatedMessages(Paginated[MessageResponse]):
    """分页消息列表（买卖家历史）。"""

    model_config = ConfigDict(title="PaginatedMessages")
