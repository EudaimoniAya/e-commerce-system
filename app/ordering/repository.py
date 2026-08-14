"""ordering 域仓储层：Order / OrderItem CRUD、条件状态更新。"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.models import Order, OrderItem


class OrderRepository:
    """订单仓储（orders 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, order: Order) -> None:
        """持久化新订单（含 OrderItem cascade，service 须先 add）。"""
        self._session.add(order)

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        """按主键查询订单（不含 items；由调用方决定是否 eager load）。"""
        return await self._session.get(Order, order_id)

    async def list_by_buyer(
        self,
        buyer_user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Order], int]:
        """返回买家订单分页列表及总数。"""
        uid = str(buyer_user_id)
        count_stmt = (
            select(func.count()).select_from(Order).where(Order.buyer_user_id == uid)
        )
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = (
            select(Order)
            .where(Order.buyer_user_id == uid)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        rows: Sequence[Order] = result.scalars().all()
        return list(rows), total

    async def list_by_shop(
        self,
        shop_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Order], int]:
        """返回店铺订单分页列表及总数。"""
        sid = str(shop_id)
        count_stmt = select(func.count()).select_from(Order).where(Order.shop_id == sid)
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = (
            select(Order)
            .where(Order.shop_id == sid)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        rows: Sequence[Order] = result.scalars().all()
        return list(rows), total

    async def update_status(
        self,
        order_id: uuid.UUID,
        from_statuses: set[str],
        to_status: str,
        *,
        cancel_reason: str | None = None,
    ) -> bool:
        """条件更新订单状态。

        ``UPDATE orders SET status=to_status … WHERE id=? AND status IN from_statuses``。
        返回 True 表示成功更新一行（抢到锁），False 表示无匹配行。
        cancel_reason 仅在 to_status == 'cancelled' 时写入。
        """
        values: dict = {"status": to_status}
        if cancel_reason is not None:
            values["cancel_reason"] = cancel_reason

        stmt = (
            update(Order)
            .where(Order.id == str(order_id), Order.status.in_(from_statuses))
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return result.rowcount == 1

    async def list_by_checkout_batch_id(
        self,
        batch_id: uuid.UUID,
    ) -> list[Order]:
        """按 checkout_batch_id 查询所有子订单（不含 items）。"""
        stmt = (
            select(Order)
            .where(Order.checkout_batch_id == str(batch_id))
            .order_by(Order.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def batch_update_status(
        self,
        order_ids: list[uuid.UUID],
        from_statuses: set[str],
        to_status: str,
    ) -> int:
        """批量条件更新订单状态。

        ``UPDATE orders SET status=to_status
        WHERE id IN (order_ids) AND status IN from_statuses``。
        返回实际更新的行数；若返回值 < len(order_ids)，说明部分订单条件不满足。
        """
        stmt = (
            update(Order)
            .where(
                Order.id.in_([str(oid) for oid in order_ids]),
                Order.status.in_(from_statuses),
            )
            .values(status=to_status)
        )
        result = await self._session.execute(stmt)
        return result.rowcount


class OrderItemRepository:
    """订单行仓储（order_items 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, item: OrderItem) -> None:
        """持久化新订单行。"""
        self._session.add(item)

    async def list_by_order_id(
        self,
        order_id: uuid.UUID,
    ) -> list[OrderItem]:
        """按订单 ID 查询所有行。"""
        stmt = select(OrderItem).where(OrderItem.order_id == str(order_id))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
