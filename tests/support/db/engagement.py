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


async def seed_browse_history(
    session: AsyncSession,
    *,
    user_id: str,
    product_id: str,
    first_viewed_at: datetime | None = None,
    last_viewed_at: datetime | None = None,
    view_count: int = 1,
) -> str:
    """INSERT user_browse_history 行（raw SQL，待 ORM 模型就绪后改为 model-based），返回 browse id。

    Args:
        session: 与 ``integration_client`` 共用同一事务的 AsyncSession。
        user_id: 浏览用户 UUID。
        product_id: 浏览商品 UUID（无 FK 约束，可用任意 UUID 构造 not_found 场景）。
        first_viewed_at: 首次浏览时间；默认当前时间，Insert 后不更新。
        last_viewed_at: 最近浏览时间；默认当前时间。测试可传入过去时间构造
            debounce（数秒前）、递增（数小时前）、间断重置（超 retention）场景。
        view_count: 累计浏览次数；默认 1。
    """
    browse_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    if first_viewed_at is None:
        first_viewed_at = now
    if last_viewed_at is None:
        last_viewed_at = now
    stmt = text(
        "INSERT INTO user_browse_history "
        "(id, user_id, product_id, first_viewed_at, last_viewed_at, view_count) "
        "VALUES (:id, :user_id, :product_id, :first_viewed_at, :last_viewed_at, :view_count)"
    )
    await session.execute(
        stmt,
        {
            "id": browse_id,
            "user_id": user_id,
            "product_id": product_id,
            "first_viewed_at": first_viewed_at,
            "last_viewed_at": last_viewed_at,
            "view_count": view_count,
        },
    )
    await session.flush()
    return browse_id


# ── 断言读（Assert：Case 内经 db_session 读取 DB 状态）──────────

async def get_browse_history(
    session: AsyncSession,
    *,
    user_id: str,
    product_id: str,
) -> dict | None:
    """读取单个 user_browse_history 行，返回 dict（含 id/first_viewed_at/last_viewed_at/view_count）。

    raw SQL——待 ORM 模型就绪后改为 model-based。未命中返回 ``None``。
    """
    stmt = text(
        "SELECT id, first_viewed_at, last_viewed_at, view_count "
        "FROM user_browse_history "
        "WHERE user_id = :user_id AND product_id = :product_id"
    )
    result = await session.execute(
        stmt,
        {"user_id": user_id, "product_id": product_id},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return dict(row)
