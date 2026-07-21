"""ordering 域 ORM 模型：Order、OrderItem。"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class Order(Base):
    """映射 `orders` 表——订单主表。"""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_buyer_user_id", "buyer_user_id"),
        Index("ix_orders_shop_id", "shop_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("shops.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="awaiting_payment",
        server_default="awaiting_payment",
    )
    initiated_by: Mapped[str] = mapped_column(
        String(16),
        default="buyer",
        server_default="buyer",
        nullable=False,
    )
    cancel_reason: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrderItem(Base):
    """映射 `order_items` 表——订单行快照。"""

    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("orders.id"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
