"""media 域仓储层：MediaAsset CRUD。"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.models import MediaAsset


class MediaRepository:
    """媒体资产仓储（media_assets 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, asset: MediaAsset) -> None:
        """持久化新 media_assets 行。"""
        self._session.add(asset)

    async def get_by_id(self, media_id: uuid.UUID) -> MediaAsset | None:
        """按主键查询媒体资产。"""
        stmt = select(MediaAsset).where(MediaAsset.id == str(media_id))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_id(self, media_id: uuid.UUID) -> bool:
        """按主键删除 media_assets 行。返回 True 表示删除了至少一行。"""
        stmt = delete(MediaAsset).where(MediaAsset.id == str(media_id))
        result = await self._session.execute(stmt)
        return result.rowcount > 0
