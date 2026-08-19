"""ai 域 retrieval service：``retrieve_chunks``（Change 3 知识类意图消费入口）。

检索契约（design D13 / spec ai-rag-retrieval）：

- 强制 shop 过滤：SQL 层 ``WHERE shop_id``（ACL，ADR-007）。
- ``score`` 为余弦距离（``<=>`` 语义：越小越相关，升序）。
- 空 query / 空库 → ``[]`` 不抛错；``top_k`` 上限 20 超限钳制。
- query 经 ``get_embedder()`` 转向量（**不**硬编码维度，spec）。
- 读路径经 ``get_ai_session_factory()``（**不**新建 PG engine）。
"""

from app.ai.rag.retrieval.repository import ProductEmbeddingChunkSearchRepository
from app.ai.rag.schemas import RetrievedChunk
from app.infra.ai_database import get_ai_session_factory
from app.infra.embedder import get_embedder

_DEFAULT_TOP_K = 5
_MAX_TOP_K = 20


async def retrieve_chunks(
    shop_id: str,
    query: str,
    top_k: int = _DEFAULT_TOP_K,
) -> list[RetrievedChunk]:
    """按店检索 top-K chunk（Change 3 客服 agent 知识类意图消费入口）。

    Args:
        shop_id: 会话绑定店铺（ACL 键，SQL 层强制过滤）。
        query: 用户查询文本；空串/纯空白 → 返回 ``[]``（不 embed 空文本）。
        top_k: 期望返回数，默认 5；超上限（20）钳制到上限，不抛错。
    """
    if not query.strip():
        return []
    effective_top_k = min(max(top_k, 1), _MAX_TOP_K)

    query_embedding = get_embedder().embed_texts([query])[0]

    async with get_ai_session_factory()() as session:
        hits = await ProductEmbeddingChunkSearchRepository(session).vector_search(
            shop_id=shop_id,
            embedding=query_embedding,
            top_k=effective_top_k,
        )

    return [
        RetrievedChunk(
            shop_id=hit.shop_id,
            product_id=hit.product_id,
            document_id=hit.document_id,
            chunk_index=hit.chunk_index,
            content_text=hit.content_text,
            score=hit.score,
        )
        for hit in hits
    ]
