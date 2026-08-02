"""engagement 域仓储层：UserFavorite CRUD。"""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.models import UserFavorite


class FavoriteRepository:
    """收藏仓储（user_favorites 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_and_product(
        self,
        user_id: uuid.UUID,
        product_id: str,
    ) -> UserFavorite | None:
        """按 (user_id, product_id) 查唯一行（重复收藏幂等校验）。"""
        stmt = select(UserFavorite).where(
            UserFavorite.user_id == str(user_id),
            UserFavorite.product_id == product_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, favorite: UserFavorite) -> None:
        """持久化新收藏行。"""
        self._session.add(favorite)

    async def delete(self, favorite: UserFavorite) -> None:
        """删除收藏行。"""
        await self._session.delete(favorite)

    async def list_page(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[UserFavorite], int]:
        """分页查询该用户全部收藏（created_at DESC）+ total 计数。

        Returns:
            (favorites, total)：``total`` 为该用户全部 favorite 行数（含 unavailable），不受分页影响。
        """
        base = select(UserFavorite).where(UserFavorite.user_id == str(user_id))
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = int(count_result.scalar_one())
        result = await self._session.execute(
            base.order_by(UserFavorite.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def delete_by_product_ids(
        self,
        user_id: uuid.UUID,
        product_ids: list[str],
    ) -> int:
        """批量删除该用户收藏中 product_id 落在列表内的行。

        未收藏过的 product_id 跳过（不导致整批失败）。返回实际删除行数。
        """
        if not product_ids:
            return 0
        stmt = delete(UserFavorite).where(
            UserFavorite.user_id == str(user_id),
            UserFavorite.product_id.in_(product_ids),
        )
        result = await self._session.execute(stmt)
        return result.rowcount
