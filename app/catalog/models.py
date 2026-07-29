"""catalog 域 ORM 模型。"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.database import Base


class Shop(Base):
    """映射 `shops` 表。"""

    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        server_default="active",
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


class Category(Base):
    """映射 `categories` 表（平台统一类目树，adjacency list）。"""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_categories_parent_id_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        String(36),
        ForeignKey("categories.id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Product(Base):
    """映射 `products` 表（商品归属店铺）。"""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_shop_id", "shop_id"),
        Index("ix_products_is_published", "is_published"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid.uuid4,
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("shops.id"),
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer)
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProductCategory(Base):
    """映射 `product_categories` 关联表（商品与类目多对多，含主类目标记）。"""

    __tablename__ = "product_categories"

    product_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("products.id"),
        primary_key=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        String(36),
        ForeignKey("categories.id"),
        primary_key=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
    )
