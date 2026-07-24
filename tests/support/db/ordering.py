"""ordering 域 DB 状态断言 helper（使用与 override 相同的 AsyncSession）。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.models import Order


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


async def get_order_status(
    session: AsyncSession,
    order_id: str,
) -> str | None:
    """查询订单 ``status``，不存在时返回 None。"""
    stmt = select(Order.status).where(Order.id == str(order_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
