"""engagement 域 ORM 模型：UserFavorite。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class UserFavorite(Base):
    """映射 `user_favorites` 表——用户对商品的收藏行。

    约束：``UNIQUE(user_id, product_id)``（一用户一商品仅一行，天然幂等）。
    索引：``ix_user_favorites_user_id``（列表按 ``created_at DESC`` 排序）。

    不存 price/name/image 快照；不声明跨域 SQLAlchemy relationship（仅存 ID）。
    """

    __tablename__ = "user_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        Index("ix_user_favorites_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
