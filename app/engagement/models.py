"""engagement 域 ORM 模型：UserFavorite、UserBrowseHistory。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


class UserBrowseHistory(Base):
    """映射 `user_browse_history` 表——用户对商品的浏览足迹。

    约束：``UNIQUE(user_id, product_id)``（一用户一商品仅一行，upsert 幂等）。
    索引：``ix_user_browse_history_user_id_last_viewed``（``(user_id, last_viewed_at)``；列表按最近浏览降序，
    由 MySQL 反向扫描实现，Alembic autogenerate 可正常比对）。

    时间戳由应用显式写入（供 debounce/间断重置计算），无 server_default；
    ``view_count`` 语义为「间断重置累计」——距上次查看超过 retention 则归 1。
    不存 price/name/image 快照；不声明跨域 SQLAlchemy relationship（仅存 ID）。
    """

    __tablename__ = "user_browse_history"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),
        Index(
            "ix_user_browse_history_user_id_last_viewed",
            "user_id",
            "last_viewed_at",
        ),
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
    first_viewed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    last_viewed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    view_count: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
