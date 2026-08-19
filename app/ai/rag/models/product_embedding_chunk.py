"""AI 读库 ``product_embedding_chunks`` 表 ORM（继承 infra ``AiBase``）。

表由 ``alembic_ai/002`` 管理（**SHALL NOT** 经 MySQL Alembic 创建）。
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infra.ai_database import AiBase

# 与 Settings.embedding_dimension / migration 001 均钉在 1024；
# 变更维度须新 revision + 全量 reindex（见 infra-ai-pgvector design Decision 4/6）。
_EMBEDDING_DIMENSION = 1024


class ProductEmbeddingChunk(AiBase):
    """映射 ``product_embedding_chunks`` 表——商品语料 chunk + 向量。

    - ``shop_id`` 为派生数据（来自商品归属，单一事实源在 MySQL ``products``），
      一致性靠 reindex 重建（ADR-011 派生数据）。
    - ``document_id`` 命名空间由 ``source_kind`` 消歧：``catalog_text`` 的
      document_id=product_id；``media_document`` 的 document_id=附件 UUID。
    """

    __tablename__ = "product_embedding_chunks"
    __table_args__ = (
        UniqueConstraint(
            "shop_id",
            "product_id",
            "document_id",
            "chunk_index",
            name="uq_product_embedding_chunks_document_chunk",
        ),
        Index("ix_product_embedding_chunks_shop_id", "shop_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(_EMBEDDING_DIMENSION),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
