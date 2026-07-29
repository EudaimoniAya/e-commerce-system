"""ordering 域 cart 仓储层：CartItem CRUD。"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.models import CartItem


class CartRepository:
    """购物车仓储（cart_items 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, item: CartItem) -> None:
        """持久化新 cart item。"""
        self._session.add(item)

    async def get_by_id(self, cart_item_id: uuid.UUID) -> CartItem | None:
        """按主键查询。"""
        return await self._session.get(CartItem, cart_item_id)

    async def list_by_user_id(self, user_id: uuid.UUID) -> list[CartItem]:
        """按用户查询全部 cart 行（按创建时间升序）。"""
        stmt = (
            select(CartItem)
            .where(CartItem.user_id == str(user_id))
            .order_by(CartItem.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user_and_product(
        self,
        user_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> CartItem | None:
        """按 (user_id, product_id) 查唯一行（用于重复加购校验）。"""
        stmt = select(CartItem).where(
            CartItem.user_id == str(user_id),
            CartItem.product_id == str(product_id),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, item: CartItem) -> None:
        """删除 cart item 行。"""
        await self._session.delete(item)

    async def delete_batch(self, cart_item_ids: list[uuid.UUID]) -> None:
        """批量删除 cart items（用于 checkout）。"""
        if not cart_item_ids:
            return
        stmt = delete(CartItem).where(
            CartItem.id.in_([str(cid) for cid in cart_item_ids])
        )
        await self._session.execute(stmt)
