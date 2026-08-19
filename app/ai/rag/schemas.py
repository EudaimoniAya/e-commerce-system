"""ai 域 RAG 管线 DTO（schemas）。

数据流：DocumentIR（摄入层收敛）→ split_document_to_chunks → ProductChunkDraft[]
→ embed/insert → product_embedding_chunks → retrieve_chunks → RetrievedChunk[]（Change 3 消费）。
"""

from typing import Any

from pydantic import BaseModel, Field


class DocumentIR(BaseModel):
    """统一中间表示：多源语料收敛点（IR 之后单管线）。

    - ``source_kind``：``catalog_text``（document_id=product_id）| ``media_document``
      （document_id=附件 UUID）；命名空间由 source_kind 消歧（design D5）。
    - ``content_text``：纯文本（chunking 输入）；**不含** price/stock 等交易属性
      （design D2 语料边界）。
    - ``shop_id``：ACL 键（派生数据，来自商品归属，ADR-011）。
    """

    document_id: str
    shop_id: str
    product_id: str
    source_kind: str
    content_text: str
    meta: dict[str, Any] = Field(default_factory=dict)


class ProductChunkDraft(BaseModel):
    """chunking 产物：单个 chunk 草稿（待 embed + insert，Task 7）。

    ``chunk_index`` 从 0 递增；同一 document 的 chunk 数受 RAG_CHUNK_MAX_CHARS 约束。
    """

    shop_id: str
    product_id: str
    document_id: str
    source_kind: str
    chunk_index: int
    content_text: str


class RetrievedChunk(BaseModel):
    """检索结果 DTO（Change 3 客服 agent 知识类意图消费）。

    ``score`` 为余弦距离（pgvector ``<=>`` 语义）：**越小越相关**，
    结果按 score 升序返回（design D13）。
    """

    shop_id: str
    product_id: str
    document_id: str
    chunk_index: int
    content_text: str
    score: float


class ReindexStats(BaseModel):
    """reindex 统计：处理/插入/跳过文档数与错误明细。

    解析失败/无效 product_id 的 document 计入 ``documents_skipped`` 与 ``errors``
    （不阻塞整店 reindex，spec ai-rag-indexing）。
    """

    documents_processed: int = 0
    chunks_inserted: int = 0
    documents_skipped: int = 0
    errors: list[str] = Field(default_factory=list)
