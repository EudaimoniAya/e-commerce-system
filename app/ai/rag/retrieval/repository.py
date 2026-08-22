"""ai 域 retrieval 仓储：pgvector 暴力 top-K 检索（按会话范围过滤）。

MVP 暴力 top-K（``<=>`` + ORDER BY + LIMIT），**无** HNSW/IVFFlat 向量索引
（design D9，Change 4+ 评估 ANN）。
"""

import uuid
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.models.product_embedding_chunk import ProductEmbeddingChunk


class SearchHit(NamedTuple):
    """单条检索命中（score 为余弦距离，越小越相关）。"""

    shop_id: str
    product_id: str
    document_id: str
    chunk_index: int
    content_text: str
    score: float


class ProductEmbeddingChunkSearchRepository:
    """``product_embedding_chunks`` 向量检索仓储（AI 读库）。

    由调用方持有 AI AsyncSession（``get_ai_session_factory``，spec：**SHALL NOT**
    在 retrieval 模块新建 PG engine）。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def vector_search(
        self,
        *,
        shop_id: str | uuid.UUID,
        embedding: list[float],
        top_k: int,
        product_id: str | uuid.UUID | None = None,
    ) -> list[SearchHit]:
        """按会话范围 top-K 检索。

        - **SQL 层强制 ``WHERE shop_id``**（spec「SQL 层 shop_id 过滤」）——即便其它店
          向量更相似也 SHALL NOT 返回（design D10 / ADR-007 店铺隔离）。
        - 传入 ``product_id`` 时再 AND 该列（商品对话）；省略则仅按店（店铺泛咨询）。
        - score 为余弦距离（``<=>`` 语义：**越小越相关**），结果按 score 升序返回
          （design D13）。
        """
        score_expr = ProductEmbeddingChunk.embedding.cosine_distance(embedding).label(
            "score"
        )
        shop_uuid = shop_id if isinstance(shop_id, uuid.UUID) else uuid.UUID(shop_id)
        filters = [ProductEmbeddingChunk.shop_id == shop_uuid]
        if product_id is not None:
            product_uuid = (
                product_id
                if isinstance(product_id, uuid.UUID)
                else uuid.UUID(product_id)
            )
            filters.append(ProductEmbeddingChunk.product_id == product_uuid)
        stmt = (
            select(
                ProductEmbeddingChunk.shop_id,
                ProductEmbeddingChunk.product_id,
                ProductEmbeddingChunk.document_id,
                ProductEmbeddingChunk.chunk_index,
                ProductEmbeddingChunk.content_text,
                score_expr,
            )
            .where(*filters)
            .order_by(score_expr.asc())
            .limit(top_k)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            SearchHit(
                shop_id=str(row.shop_id),
                product_id=str(row.product_id),
                document_id=str(row.document_id),
                chunk_index=row.chunk_index,
                content_text=row.content_text,
                score=float(row.score),
            )
            for row in rows
        ]
