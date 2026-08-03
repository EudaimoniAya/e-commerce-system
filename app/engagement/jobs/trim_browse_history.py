"""engagement 域定时任务：按 top N + retention 裁剪 `user_browse_history`。

算法（按 user_id 分组）：
1. 取该用户全部 browse 行，按 ``last_viewed_at DESC`` 排序
2. top ``BROWSE_HISTORY_MAX_PER_USER`` 行 → 保留（无论是否超 retention）
3. 其余行中，``last_viewed_at < retention_cutoff`` → 删除

模块组成：
- ``BrowseTrimRow``：纯函数输入的行值对象（与 ORM 解耦）
- ``plan_browse_trim_deletes``：纯函数，返回应删除的行（无 I/O，可单测）
- ``trim_browse_history``：async session 入口，读配置、映射 ORM 行、删除、提交
- ``__main__``：CLI，供 ``task browse:trim`` 调用
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.models import UserBrowseHistory
from app.infra.config import get_settings
from app.infra.database import get_session_factory


@dataclass(frozen=True)
class BrowseTrimRow:
    """裁剪算法的输入行（轻量值对象，只含分组/排序/判期所需字段）。"""

    id: str
    user_id: str
    last_viewed_at: datetime


def plan_browse_trim_deletes(
    rows: list[BrowseTrimRow],
    *,
    max_per_user: int,
    retention_cutoff: datetime,
) -> set[str]:
    """纯函数：返回应删除的 browse 行 id 集合（无 I/O）。

    对 ``rows`` 按 ``user_id`` 分组，每组按 ``last_viewed_at DESC`` 排序：
    - 前 ``max_per_user`` 行无条件保留（top N 内行即使超 retention 也保留，直至被挤出 top N）
    - 其余行中，``last_viewed_at < retention_cutoff`` 者返回其 id
      （超出 top N 但未超期者保留，待后续 trim 时机到达再删）

    Args:
        rows: 参与裁剪的全部 browse 行。
        max_per_user: 每用户保留的最近行数上限。
        retention_cutoff: retention 截止时刻（``now - timedelta(days=BROWSE_HISTORY_RETENTION_DAYS)``）。

    Returns:
        应删除行的 id 集合。
    """
    by_user: dict[str, list[BrowseTrimRow]] = {}
    for row in rows:
        by_user.setdefault(row.user_id, []).append(row)

    to_delete: set[str] = set()
    for user_rows in by_user.values():
        user_rows.sort(key=lambda r: r.last_viewed_at, reverse=True)
        for row in user_rows[max_per_user:]:
            if row.last_viewed_at < retention_cutoff:
                to_delete.add(row.id)
    return to_delete


async def trim_browse_history(session: AsyncSession) -> int:
    """async session 入口：加载全部 browse 行，裁剪超 N 且超期行并提交。

    Returns:
        实际删除行数。
    """
    settings = get_settings()
    retention_cutoff = datetime.now() - timedelta(
        days=settings.browse_history_retention_days
    )

    result = await session.execute(select(UserBrowseHistory))
    orm_rows = list(result.scalars().all())
    if not orm_rows:
        return 0

    rows = [
        BrowseTrimRow(
            id=str(r.id),
            user_id=str(r.user_id),
            last_viewed_at=r.last_viewed_at,
        )
        for r in orm_rows
    ]
    delete_ids = plan_browse_trim_deletes(
        rows,
        max_per_user=settings.browse_history_max_per_user,
        retention_cutoff=retention_cutoff,
    )
    for row in orm_rows:
        if str(row.id) in delete_ids:
            await session.delete(row)
    await session.commit()
    return len(delete_ids)


async def _run_cli() -> None:
    """CLI 入口：独立 session 执行 trim 并打印统计。"""
    settings = get_settings()
    async with get_session_factory()() as session:
        deleted = await trim_browse_history(session)
    print(
        f"browse:trim done — deleted {deleted} row(s) "
        f"(max_per_user={settings.browse_history_max_per_user}, "
        f"retention_days={settings.browse_history_retention_days})"
    )


if __name__ == "__main__":
    asyncio.run(_run_cli())
