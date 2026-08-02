"""engagement 域 DB seed / 断言 helper（使用与 override 相同的 AsyncSession）。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── Seed（Arrange：直写 SAVEPOINT session，不经 HTTP）──────────

async def seed_favorite(
    session: AsyncSession,
    *,
    user_id: str,
    product_id: str,
    created_at: datetime | None = None,
) -> str:
    """INSERT user_favorites 行（raw SQL，待 ORM 模型就绪后改为 model-based），返回 favorite id。

    Args:
        session: 与 ``integration_client`` 共用同一事务的 AsyncSession。
        user_id: 收藏用户 UUID。
        product_id: 收藏商品 UUID（无 FK 约束，可用任意 UUID 构造 not_found 场景）。
        created_at: 收藏时间；默认当前时间。测试可传入过去时间构造 ``created_at DESC`` 场景。
    """
    favorite_id = str(uuid.uuid4())
    if created_at is None:
        created_at = datetime.now(UTC)
    stmt = text(
        "INSERT INTO user_favorites (id, user_id, product_id, created_at) "
        "VALUES (:id, :user_id, :product_id, :created_at)"
    )
    await session.execute(
        stmt,
        {
            "id": favorite_id,
            "user_id": user_id,
            "product_id": product_id,
            "created_at": created_at,
        },
    )
    await session.flush()
    return favorite_id
