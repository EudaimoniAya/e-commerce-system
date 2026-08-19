"""ai 域服务门面：面向 Change 3 消费方与 ai 域内部接口。

- ``retrieve_chunks``：Change 3 客服 agent 知识类意图消费入口（Task 8 落地）。
- ``delete_product_chunks`` / ``delete_document_chunks``：ai 域**内部**清理接口
  （design D8 / spec ai-rag-indexing：**业务域 SHALL NOT 调用**，本 change 无业务域
  调用方；供未来删除路径 / 事件驱动（ADR-009 Outbox）接线）。
"""

import uuid

from app.ai.rag.indexing.repository import ProductEmbeddingChunkRepository
from app.ai.rag.retrieval.service import retrieve_chunks as _retrieve_chunks
from app.ai.rag.schemas import RetrievedChunk
from app.infra.ai_database import get_ai_session_factory


async def retrieve_chunks(
    shop_id: str,
    query: str,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Change 3 客服 agent 知识类意图消费入口（design D13）。

    转发至 retrieval service（ACL 强制 shop 过滤）；**NOT** support 域直调
    （业务域不 import ai，support 经 Change 3 handler 注册表分派）。
    """
    return await _retrieve_chunks(shop_id=shop_id, query=query, top_k=top_k)


async def delete_product_chunks(product_id: str) -> None:
    """ai 域内部：清该商品全部 document 的 chunk。

    商品下架/删除后的 chunk 清理由 reindex 语义承担（业务域零 ai 依赖，design D8）；
    本接口保留供未来删除路径 / 事件驱动接线，本 change 无业务域调用方。
    """
    async with get_ai_session_factory()() as session:
        await ProductEmbeddingChunkRepository(session).delete_by_product(
            product_id=uuid.UUID(product_id)
        )
        await session.commit()


async def delete_document_chunks(source_kind: str, document_id: str) -> None:
    """ai 域内部：按 ``(source_kind, document_id)`` 清 chunk。

    ``document_id`` 命名空间由 ``source_kind`` 消歧（design D5）：
    catalog_text 的 document_id=product_id、media_document 的 document_id=附件 UUID。
    """
    async with get_ai_session_factory()() as session:
        await ProductEmbeddingChunkRepository(session).delete_by_document_ref(
            source_kind=source_kind,
            document_id=uuid.UUID(document_id),
        )
        await session.commit()
