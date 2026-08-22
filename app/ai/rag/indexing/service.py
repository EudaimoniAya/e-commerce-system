"""ai 域 indexing service：多源语料摄入与 reindex 编排（Task 6/7）。

数据流（design §17）：业务域 DTO → ``DocumentIR`` → ``split_document_to_chunks``
→ embed → ``product_embedding_chunks``；per document delete-then-insert（design D8）。

跨域纪律：经 catalog service（``list_products_for_rag_indexing`` /
``get_product_for_rag_indexing``）与传入的 ``MediaService`` 取数；
**不** import 业务域 ORM/repository。MediaService 由 ``app.ai.deps`` 装配后传入。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.chunking import split_document_to_chunks
from app.ai.rag.indexing.repository import ProductEmbeddingChunkRepository
from app.ai.rag.models.product_embedding_chunk import ProductEmbeddingChunk
from app.ai.rag.parsing import parse_document
from app.ai.rag.schemas import (
    SOURCE_KIND_CATALOG_TEXT,
    SOURCE_KIND_MEDIA_DOCUMENT,
    DocumentIR,
    ReindexStats,
)
from app.catalog.product_service import (
    get_product_for_rag_indexing,
    list_products_for_rag_indexing,
)
from app.catalog.schemas import ProductRagSource
from app.infra.ai_database import get_ai_session_factory
from app.infra.embedder import Embedder, get_embedder
from app.media.service import MediaService


async def media_documents_for_product(
    *,
    product_id: str,
    shop_id: str,
    media_service: MediaService,
    stats: ReindexStats | None = None,
) -> list[DocumentIR]:
    """拉取商品关联文档并解析为 ``DocumentIR``（``source_kind=media_document``）。

    经 media 数据提供接口（``list_documents_by_product`` + ``get_file_stream``），
    ai 域**不** import media ORM/repository（跨域纪律）。
    店级隔离由调用方（catalog 已上架商品列表）保证——media 无 shop_id（ADR-011 §6）。
    解析失败/空文本的 document 跳过；传入 ``stats`` 时跳过计入 ``ReindexStats``
    （spec：解析失败该 document SHALL 被跳过并计入 reindex 统计）。
    """
    documents = await media_service.list_documents_by_product(product_id)

    irds: list[DocumentIR] = []
    for document in documents:
        data, _ = await media_service.get_file_stream(document.asset_id)
        text = parse_document(document.content_type, data)
        if not text:
            if stats is not None:
                stats.documents_skipped += 1
                stats.errors.append(
                    f"解析失败/空文本 media_document={document.asset_id}"
                )
            continue
        irds.append(
            DocumentIR(
                document_id=document.asset_id,  # media_document: document_id=附件 UUID
                shop_id=shop_id,
                product_id=product_id,
                source_kind=SOURCE_KIND_MEDIA_DOCUMENT,
                content_text=text,
                meta={},
            )
        )
    return irds


async def reindex_product(
    product_id: str,
    *,
    db_session: AsyncSession,
    media_service: MediaService,
) -> ReindexStats:
    """重建单商品全部 document（catalog_text + 关联 media_document），per document 重建。

    - 商品已上架：catalog_text + 每个 media_document 各 delete-then-insert。
    - 商品未上架/不存在：净删该商品全部 chunk（不使用 media_service）。
    """
    stats = ReindexStats()
    product = await get_product_for_rag_indexing(product_id, session=db_session)
    async with get_ai_session_factory()() as ai_session:
        repository = ProductEmbeddingChunkRepository(ai_session)
        embedder = get_embedder()

        if product is None:
            await repository.delete_by_product(product_id=uuid.UUID(product_id))
            stats.documents_skipped += 1
            stats.errors.append(
                f"商品未上架/不存在 product_id={product_id}，清除其 chunk"
            )
            await ai_session.commit()
            return stats

        await _reindex_product_documents(
            product,
            repository=repository,
            embedder=embedder,
            media_service=media_service,
            stats=stats,
        )
        await ai_session.commit()
    return stats


async def reindex_shop(
    shop_id: str,
    *,
    db_session: AsyncSession,
    media_service: MediaService,
) -> ReindexStats:
    """整店重建（catalog_text + media_document 全量，含 orphan 扫描）。

    1. orphan 扫描：按商品上架状态清理下架商品 chunk；``source_kind=media_document``
       从 PG 反枚举 document_id → 经 media 单资产查询（``asset_exists``）逐条校验
       附件存在性 → 不存在则删 chunk。
    2. 逐商品双源 delete-then-insert。
    """
    stats = ReindexStats()

    products = await list_products_for_rag_indexing(shop_id=shop_id, session=db_session)
    published_ids = {product.product_id for product in products}

    async with get_ai_session_factory()() as ai_session:
        repository = ProductEmbeddingChunkRepository(ai_session)
        embedder = get_embedder()

        for (
            product_id,
            source_kind,
            document_id,
        ) in await repository.list_documents_for_shop(shop_id=shop_id):
            if product_id not in published_ids:
                await repository.delete_by_document(
                    shop_id=uuid.UUID(shop_id),
                    product_id=uuid.UUID(product_id),
                    document_id=uuid.UUID(document_id),
                )
                stats.documents_skipped += 1
                stats.errors.append(
                    f"orphan 下架商品 product_id={product_id} 清除 chunk"
                )
                continue
            if source_kind == SOURCE_KIND_MEDIA_DOCUMENT:
                if not await media_service.asset_exists(document_id):
                    await repository.delete_by_document(
                        shop_id=uuid.UUID(shop_id),
                        product_id=uuid.UUID(product_id),
                        document_id=uuid.UUID(document_id),
                    )
                    stats.documents_skipped += 1
                    stats.errors.append(
                        f"orphan 附件已删除 document_id={document_id} 清除 chunk"
                    )

        for product in products:
            await _reindex_product_documents(
                product,
                repository=repository,
                embedder=embedder,
                media_service=media_service,
                stats=stats,
            )
        await ai_session.commit()
    return stats


async def reindex_document(
    source_kind: str,
    document_id: str,
    *,
    db_session: AsyncSession,
    media_service: MediaService,
) -> ReindexStats:
    """重建单文档（``document_id`` 命名空间由 ``source_kind`` 消歧，design D5）。

    - ``catalog_text``：document_id=product_id；商品未上架/不存在 → 净删该商品全部 chunk。
    - ``media_document``：document_id=附件 UUID；从 PG 反查归属（media 域无反向接口），
      无法定位（从未索引过）→ 跳过；商品未上架/附件已删/解析失败 → 净删该文档 chunk。
    """
    stats = ReindexStats()

    async with get_ai_session_factory()() as ai_session:
        repository = ProductEmbeddingChunkRepository(ai_session)
        embedder = get_embedder()

        if source_kind == SOURCE_KIND_CATALOG_TEXT:
            await _reindex_catalog_document(
                document_id=document_id,
                db_session=db_session,
                repository=repository,
                embedder=embedder,
                stats=stats,
            )
        elif source_kind == SOURCE_KIND_MEDIA_DOCUMENT:
            await _reindex_media_document(
                document_id=document_id,
                db_session=db_session,
                repository=repository,
                embedder=embedder,
                media_service=media_service,
                stats=stats,
            )
        else:
            raise ValueError(f"不支持的 source_kind: {source_kind}")

        await ai_session.commit()
    return stats


# ── 内部：双源 DocumentIR 组装 / 单文档写入 ─────────────────────────────────


async def _reindex_product_documents(
    product: ProductRagSource,
    *,
    repository: ProductEmbeddingChunkRepository,
    embedder: Embedder,
    media_service: MediaService,
    stats: ReindexStats,
) -> None:
    """单商品双源重建：catalog_text + media_document（design §17.3 统一收敛）。"""
    await _write_document(
        _catalog_ir(product),
        repository=repository,
        embedder=embedder,
        stats=stats,
    )
    media_docs = await media_documents_for_product(
        product_id=product.product_id,
        shop_id=product.shop_id,
        media_service=media_service,
        stats=stats,
    )
    for document in media_docs:
        await _write_document(
            document,
            repository=repository,
            embedder=embedder,
            stats=stats,
        )


async def _reindex_catalog_document(
    *,
    document_id: str,
    db_session: AsyncSession,
    repository: ProductEmbeddingChunkRepository,
    embedder: Embedder,
    stats: ReindexStats,
) -> None:
    """catalog_text 单文档重建：document_id=product_id（spec reindex-document 场景）。"""
    product = await get_product_for_rag_indexing(document_id, session=db_session)
    if product is None:
        await repository.delete_by_product(product_id=uuid.UUID(document_id))
        stats.documents_skipped += 1
        stats.errors.append(f"商品未上架/不存在 product_id={document_id}，清除其 chunk")
        return
    await _write_document(
        _catalog_ir(product),
        repository=repository,
        embedder=embedder,
        stats=stats,
    )


async def _reindex_media_document(
    *,
    document_id: str,
    db_session: AsyncSession,
    repository: ProductEmbeddingChunkRepository,
    embedder: Embedder,
    media_service: MediaService,
    stats: ReindexStats,
) -> None:
    """media_document 单文档重建：document_id=附件 UUID。

    首次索引（无既有 chunk 可反查归属）走 ``reindex_product`` / ``reindex_shop``
    枚举路径——本接口面向「已知文档的重建」（Task 9 CLI）。
    """
    owner = await repository.get_document_owner(
        source_kind=SOURCE_KIND_MEDIA_DOCUMENT,
        document_id=document_id,
    )
    if owner is None:
        stats.documents_skipped += 1
        stats.errors.append(
            f"media_document={document_id} 无既有 chunk，无法定位归属，跳过"
        )
        return
    shop_id, product_id = owner

    if await get_product_for_rag_indexing(product_id, session=db_session) is None:
        await repository.delete_by_document(
            shop_id=uuid.UUID(shop_id),
            product_id=uuid.UUID(product_id),
            document_id=uuid.UUID(document_id),
        )
        stats.documents_skipped += 1
        stats.errors.append(
            f"商品未上架 product_id={product_id}，清除 media_document={document_id} chunk"
        )
        return

    if not await media_service.asset_exists(document_id):
        await repository.delete_by_document(
            shop_id=uuid.UUID(shop_id),
            product_id=uuid.UUID(product_id),
            document_id=uuid.UUID(document_id),
        )
        stats.documents_skipped += 1
        stats.errors.append(f"附件已删除 document_id={document_id}，清除其 chunk")
        return

    data, content_type = await media_service.get_file_stream(document_id)
    text = parse_document(content_type, data)
    if not text:
        await repository.delete_by_document(
            shop_id=uuid.UUID(shop_id),
            product_id=uuid.UUID(product_id),
            document_id=uuid.UUID(document_id),
        )
        stats.documents_skipped += 1
        stats.errors.append(f"解析失败/空文本 document_id={document_id}，清除其 chunk")
        return

    await _write_document(
        DocumentIR(
            document_id=document_id,
            shop_id=shop_id,
            product_id=product_id,
            source_kind=SOURCE_KIND_MEDIA_DOCUMENT,
            content_text=text,
            meta={},
        ),
        repository=repository,
        embedder=embedder,
        stats=stats,
    )


async def _write_document(
    document: DocumentIR,
    *,
    repository: ProductEmbeddingChunkRepository,
    embedder: Embedder,
    stats: ReindexStats,
) -> None:
    """per document delete-then-insert（design D8 / spec「Reindex delete-then-insert」）。

    先删 ``(shop_id, product_id, document_id)`` 既有 chunk，再 chunking → embed → insert；
    无可索引语料（空 chunk 列表）→ 净删不插入。
    """
    await repository.delete_by_document(
        shop_id=uuid.UUID(document.shop_id),
        product_id=uuid.UUID(document.product_id),
        document_id=uuid.UUID(document.document_id),
    )
    chunks = split_document_to_chunks(document)
    if not chunks:
        stats.documents_skipped += 1
        stats.errors.append(
            f"无可索引语料 source_kind={document.source_kind} "
            f"document_id={document.document_id}"
        )
        return
    vectors = embedder.embed_texts([chunk.content_text for chunk in chunks])
    rows = [
        ProductEmbeddingChunk(
            shop_id=uuid.UUID(chunk.shop_id),
            product_id=uuid.UUID(chunk.product_id),
            document_id=uuid.UUID(chunk.document_id),
            chunk_index=chunk.chunk_index,
            source_kind=chunk.source_kind,
            content_text=chunk.content_text,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await repository.bulk_insert(rows)
    stats.documents_processed += 1
    stats.chunks_inserted += len(rows)


# ── 内部：IR 组装 ──────────────────────────────────────────────────────────


def _catalog_ir(product: ProductRagSource) -> DocumentIR:
    """catalog_text 源 ``DocumentIR``：document_id=product_id（design §17.2）。"""
    return DocumentIR(
        document_id=product.product_id,  # catalog_text: document_id = product_id
        shop_id=product.shop_id,
        product_id=product.product_id,
        source_kind=SOURCE_KIND_CATALOG_TEXT,
        content_text=_assemble_catalog_text(product.name, product.description),
        meta={},
    )


def _assemble_catalog_text(name: str, description: str | None) -> str:
    """catalog 语料组装：name + description（price 丢弃——design D2 不进语料）。

    与 chunking 单测的构造约定一致（name 在 content 开头 → 首 chunk 含商品名前缀）。
    """
    return f"{name}\n{description}" if description else name
