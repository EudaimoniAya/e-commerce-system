"""catalog 域 DB seed / 断言 helper（使用与 override 相同的 AsyncSession）。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Product, ProductCategory, Shop


# ── Seed（Arrange：直写 SAVEPOINT session，不经 HTTP）──────────

async def seed_shop(
    session: AsyncSession,
    *,
    owner_user_id: str,
    name: str,
    status: str = "active",
) -> str:
    """INSERT shops 行，返回 shop_id。

    约束：``owner_user_id`` UNIQUE（一人一店），``name`` UNIQUE。
    """
    shop = Shop(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        name=name,
        status=status,
    )
    session.add(shop)
    await session.flush()
    return str(shop.id)


async def seed_category(
    session: AsyncSession,
    *,
    name: str,
    parent_id: str | None = None,
) -> str:
    """INSERT categories 行，返回 category_id。

    约束：``(parent_id, name)`` UNIQUE。根类目传 ``parent_id=None``。
    """
    cat = Category(
        id=str(uuid.uuid4()),
        name=name,
        parent_id=parent_id,
    )
    session.add(cat)
    await session.flush()
    return str(cat.id)


async def seed_product(
    session: AsyncSession,
    *,
    shop_id: str,
    name: str,
    price: str = "99.00",
    stock: int = 10,
    is_published: bool = False,
) -> str:
    """INSERT products 行，返回 product_id。"""
    from decimal import Decimal

    product = Product(
        id=str(uuid.uuid4()),
        shop_id=shop_id,
        name=name,
        price=Decimal(price),
        stock=stock,
        is_published=is_published,
    )
    session.add(product)
    await session.flush()
    return str(product.id)


async def seed_product_category(
    session: AsyncSession,
    *,
    product_id: str,
    category_id: str,
    is_primary: bool = False,
) -> None:
    """INSERT product_categories 关联行。复合 PK：``(product_id, category_id)``。"""
    pc = ProductCategory(
        product_id=product_id,
        category_id=category_id,
        is_primary=is_primary,
    )
    session.add(pc)
    await session.flush()


# ── Assert（HTTP Act 后查表验证副作用）────────────────────────

async def get_product_stock(
    session: AsyncSession,
    product_id: str,
) -> int | None:
    """查询商品 ``stock``，不存在时返回 None。"""
    stmt = select(Product.stock).where(Product.id == str(product_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
