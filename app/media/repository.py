"""media 域仓储层：MediaAsset CRUD + FK 引用计数。"""

import uuid

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.models import MediaAsset


class MediaRepository:
    """媒体资产仓储（media_assets 表）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, asset: MediaAsset) -> None:
        """持久化新 media_assets 行并立即 flush。

        flush 使行在当前事务内物理可见（autoflush 仅对 ORM 查询触发，
        原始 SQL DML 不会触发——DELETE 409 的 count_references / 业务表
        FK 引用需要行先落库）。
        """
        self._session.add(asset)
        await self._session.flush()

    async def get_by_id(
        self,
        media_id: uuid.UUID,
        *,
        fresh: bool = False,
    ) -> MediaAsset | None:
        """按主键查询媒体资产。

        fresh=True 时用 ``populate_existing`` 强制从 DB 刷新（忽略 identity map
        缓存），供 get_detail 读取当前持久化状态——测试以原始 SQL 模拟 attach 时，
        同会话共享的 ORM 对象可能是旧值。
        """
        stmt = select(MediaAsset).where(MediaAsset.id == str(media_id))
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many_by_ids(self, media_ids: list[str]) -> list[MediaAsset]:
        """按主键批量查询媒体资产（resolve_urls 用，避免 N+1）。"""
        stmt = select(MediaAsset).where(MediaAsset.id.in_(media_ids))
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def list_by_product(self, product_id: uuid.UUID) -> list[MediaAsset]:
        """按商品查询关联文档（纯 product_id 查询，无店级过滤——MediaAsset 无 shop_id）。

        供 ai 域 indexing 拉取商品文档（source_kind=media_document）；
        店级隔离由 ai 侧 catalog 已上架商品列表保证（ADR-011 §6 校验沿消费方向）。
        """
        stmt = (
            select(MediaAsset)
            .where(MediaAsset.product_id == str(product_id))
            .order_by(MediaAsset.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def count_references(self, media_id: uuid.UUID) -> int:
        """统计 media_id 被业务表 FK 引用的数量。

        只读 text SQL 查三表（users.avatar_media_id / shops.logo_media_id /
        products.primary_media_id）；**不** import catalog/user ORM（跨域纪律）。
        """
        media_id_str = str(media_id)
        total = 0
        for sql in (
            "SELECT COUNT(*) FROM users WHERE avatar_media_id = :mid",
            "SELECT COUNT(*) FROM shops WHERE logo_media_id = :mid",
            "SELECT COUNT(*) FROM products WHERE primary_media_id = :mid",
        ):
            result = await self._session.execute(text(sql), {"mid": media_id_str})
            total += result.scalar_one()
        return total

    async def delete_by_id(self, media_id: uuid.UUID) -> bool:
        """按主键删除 media_assets 行。返回 True 表示删除了至少一行。"""
        stmt = delete(MediaAsset).where(MediaAsset.id == str(media_id))
        result = await self._session.execute(stmt)
        return result.rowcount > 0
