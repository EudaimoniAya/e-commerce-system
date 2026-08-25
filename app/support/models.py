"""support 域 ORM 模型：SupportConversation、SupportMessage。

对齐 spec：
- ``support_conversations``：``UNIQUE(shop_id, buyer_user_id)``、索引 ``(shop_id, updated_at)`` 供 inbox。
- ``support_messages``：索引 ``(conversation_id, created_at)`` 供历史 ASC。
- 不声明跨域 SQLAlchemy relationship（仅存 ID）；``message_refs`` 为 JSON 列（MVP 仅 product）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class SupportConversation(Base):
    """映射 `support_conversations` 表——店铺与买家的唯一会话。

    约束：``UNIQUE(shop_id, buyer_user_id)``（一买家一店一会话）。
    索引：``ix_support_conversations_shop_updated``（``(shop_id, updated_at)`` 供 inbox 排序）。
    ``last_message_preview`` 为最近消息预览（body 截断前 200 字符；ref-only 消息可空/占位）。
    """

    __tablename__ = "support_conversations"
    __table_args__ = (
        UniqueConstraint(
            "shop_id", "buyer_user_id", name="uq_support_conversations_shop_buyer"
        ),
        Index("ix_support_conversations_shop_updated", "shop_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        nullable=False,
    )
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        nullable=False,
    )
    handler_mode: Mapped[str] = mapped_column(
        String(16),
        default="ai",
        server_default="ai",
        nullable=False,
    )
    last_message_preview: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SupportMessage(Base):
    """映射 `support_messages` 表——会话内消息。

    ``sender_role`` 为对话侧（buyer | shop）；``author_role`` 为实际撰写者（human | ai，
    MVP 恒 human）。``body`` 与 ``message_refs`` 至少一项非空。
    """

    __tablename__ = "support_messages"
    __table_args__ = (
        Index(
            "ix_support_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        nullable=False,
    )
    sender_role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    author_role: Mapped[str] = mapped_column(
        String(16),
        default="human",
        server_default="human",
        nullable=False,
    )
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    message_refs: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        server_default=func.now(),
    )
