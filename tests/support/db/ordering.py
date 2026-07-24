"""ordering 域 DB seed / 断言 helper（使用与 override 相同的 AsyncSession）。"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.models import Order, OrderItem


# ── Seed（Arrange：直写 SAVEPOINT session，不经 HTTP）──────────

async def seed_order(
    session: AsyncSession,
    *,
    buyer_user_id: str,
    shop_id: str,
    total_amount: str = "0.00",
    expires_at: datetime | None = None,
    status: str = "awaiting_payment",
    initiated_by: str = "buyer",
) -> str:
    """INSERT orders 行，返回 order_id。

    ``expires_at`` 默认为 now + 86400 秒（1 天）。
    """
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(seconds=86400)

    order = Order(
        id=str(uuid.uuid4()),
        buyer_user_id=buyer_user_id,
        shop_id=shop_id,
        total_amount=Decimal(total_amount),
        expires_at=expires_at,
        status=status,
        initiated_by=initiated_by,
    )
    session.add(order)
    await session.flush()
    return str(order.id)


async def seed_order_item(
    session: AsyncSession,
    *,
    order_id: str,
    product_id: str,
    product_name: str,
    unit_price: str,
    qty: int,
) -> str:
    """INSERT order_items 行，返回 item_id。

    ``product_id`` 无 FK 约束（快照语义），可用任意 UUID。
    """
    item = OrderItem(
        id=str(uuid.uuid4()),
        order_id=order_id,
        product_id=product_id,
        product_name=product_name,
        unit_price=Decimal(unit_price),
        qty=qty,
    )
    session.add(item)
    await session.flush()
    return str(item.id)


# ── Manipulate（Arrange：修改已有行，模拟边界状态）────────────

async def backdate_order_expires_at(
    session: AsyncSession,
    order_id: str,
    *,
    seconds: int = 0,
) -> None:
    """将订单 ``expires_at`` 回拨到过去，模拟 TTL 过期。

    Args:
        session: 与 ``integration_client`` 共用同一事务的 AsyncSession。
        order_id: 订单 ID 字符串。
        seconds: 回拨秒数（默认最小 1 秒前）。
    """
    if seconds <= 0:
        seconds = 1
    new_expires = datetime.now(UTC) - timedelta(seconds=seconds)
    stmt = (
        update(Order)
        .where(Order.id == str(order_id))
        .values(expires_at=new_expires)
    )
    await session.execute(stmt)
    await session.flush()


# ── Assert（HTTP Act 后查表验证副作用）────────────────────────

async def get_order_status(
    session: AsyncSession,
    order_id: str,
) -> str | None:
    """查询订单 ``status``，不存在时返回 None。"""
    stmt = select(Order.status).where(Order.id == str(order_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
