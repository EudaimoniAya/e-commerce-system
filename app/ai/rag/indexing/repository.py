"""ai 域 indexing 仓储：``product_embedding_chunks`` 删除/写入/枚举（AI 读库，PG）。

由调用方持有 AI AsyncSession（``get_ai_session_factory``）；delete/insert 均在该
session 事务内，由调用方统一 commit（reindex 为跨库语义：MySQL 读源 + PG 写 chunk，
PG 侧显式 commit 使行对其它连接可见，见 design Risks「PG 清理/写入失败」）。
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.models.product_embedding_chunk import ProductEmbeddingChunk


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """归一化主键为 ``uuid.UUID``（列类型 PgUUID(as_uuid=True)）。"""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


class ProductEmbeddingChunkRepository:
    """``product_embedding_chunks`` 表仓储（Task 7.1）。

    - ``delete_by_document``：per document delete-then-insert 的删除步（design D8）。
    - ``delete_by_product`` / ``delete_by_document_ref``：ai 域内部清理接口
      （``delete_product_chunks`` / ``delete_document_chunks``，design D13）。
    - ``list_documents_for_shop``：orphan 扫描反枚举（Task 7.4）。
    - ``get_document_owner``：media_document 单文档 reindex 的归属反查。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete_by_document(
        self,
        *,
        shop_id: str | uuid.UUID,
        product_id: str | uuid.UUID,
        document_id: str | uuid.UUID,
    ) -> int:
        """删除 ``(shop_id, product_id, document_id)`` 全部 chunk（返回删除行数）。"""
        stmt = delete(ProductEmbeddingChunk).where(
            ProductEmbeddingChunk.shop_id == _as_uuid(shop_id),
            ProductEmbeddingChunk.product_id == _as_uuid(product_id),
            ProductEmbeddingChunk.document_id == _as_uuid(document_id),
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def delete_by_product(self, *, product_id: str | uuid.UUID) -> int:
        """删除某商品全部 document 的 chunk（下架清理 / ``delete_product_chunks``）。

        ``product_id`` 全局唯一（一商品仅属一店），无需 shop_id 过滤。
        """
        stmt = delete(ProductEmbeddingChunk).where(
            ProductEmbeddingChunk.product_id == _as_uuid(product_id)
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def delete_by_document_ref(
        self,
        *,
        source_kind: str,
        document_id: str | uuid.UUID,
    ) -> int:
        """按 ``(source_kind, document_id)`` 删除（``delete_document_chunks``）。

        ``document_id`` 命名空间由 ``source_kind`` 消歧（design D5）：
        catalog_text 的 document_id=product_id、media_document 的 document_id=附件 UUID。
        """
        stmt = delete(ProductEmbeddingChunk).where(
            ProductEmbeddingChunk.source_kind == source_kind,
            ProductEmbeddingChunk.document_id == _as_uuid(document_id),
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def bulk_insert(self, rows: list[ProductEmbeddingChunk]) -> None:
        """批量写入 chunk 行（调用方 commit 时落库；空列表 no-op）。"""
        if rows:
            self._session.add_all(rows)

    async def list_documents_for_shop(
        self,
        *,
        shop_id: str | uuid.UUID,
    ) -> list[tuple[str, str, str]]:
        """按店反枚举去重的 ``(product_id, source_kind, document_id)``——orphan 扫描输入。

        从 PG 现状出发（而非业务源），配合 catalog 上架列表 / media 单资产存在性
        校验清理「已下架商品 / 已删附件」的遗留 chunk（Task 7.4）。
        """
        stmt = (
            select(
                ProductEmbeddingChunk.product_id,
                ProductEmbeddingChunk.source_kind,
                ProductEmbeddingChunk.document_id,
            )
            .where(ProductEmbeddingChunk.shop_id == _as_uuid(shop_id))
            .distinct()
        )
        result = await self._session.execute(stmt)
        return [
            (str(product_id), source_kind, str(document_id))
            for product_id, source_kind, document_id in result.all()
        ]

    async def get_document_owner(
        self,
        *,
        source_kind: str,
        document_id: str | uuid.UUID,
    ) -> tuple[str, str] | None:
        """按 ``(source_kind, document_id)`` 反查归属 ``(shop_id, product_id)``。

        供 ``reindex_document(media_document)`` 定位附件所属商品（media 域无
        「附件 → 商品」反向接口，media spec 仅 product → docs 与单资产存在性查询）。
        """
        stmt = (
            select(
                ProductEmbeddingChunk.shop_id,
                ProductEmbeddingChunk.product_id,
            )
            .where(
                ProductEmbeddingChunk.source_kind == source_kind,
                ProductEmbeddingChunk.document_id == _as_uuid(document_id),
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return str(row[0]), str(row[1])
