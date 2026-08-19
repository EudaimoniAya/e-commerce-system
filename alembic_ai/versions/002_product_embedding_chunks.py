"""创建 AI 库 product_embedding_chunks 表（商品语料 chunk + 向量）。

- ``vector(1024)``：与 Settings.embedding_dimension / migration 001 一致
- ``UNIQUE(shop_id, product_id, document_id, chunk_index)``：per-document chunk 幂等
- MVP 索引：``(shop_id)`` B-tree 辅助 ACL 过滤；**无** HNSW/IVFFlat（design D9 暴力 top-K）
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_embedding_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shop_id",
            "product_id",
            "document_id",
            "chunk_index",
            name="uq_product_embedding_chunks_document_chunk",
        ),
    )
    op.create_index(
        "ix_product_embedding_chunks_shop_id",
        "product_embedding_chunks",
        ["shop_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_embedding_chunks_shop_id",
        table_name="product_embedding_chunks",
    )
    op.drop_table("product_embedding_chunks")
