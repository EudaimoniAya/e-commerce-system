"""catalog 域 DB 状态断言 helper（使用与 override 相同的 AsyncSession）。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product


async def get_product_stock(
    session: AsyncSession,
    product_id: str,
) -> int | None:
    """查询商品 ``stock``，不存在时返回 None。"""
    stmt = select(Product.stock).where(Product.id == str(product_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
