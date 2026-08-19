"""ai 域 indexing service：多源语料摄入。

Task 6 交付 media 文档拉取 adapter（media 源 → DocumentIR）；
reindex 编排（reindex_shop / reindex_product / reindex_document）在 Task 7 落地。
"""

from app.ai.rag.parsing import parse_document
from app.ai.rag.schemas import DocumentIR
from app.media.service import MediaService


async def media_documents_for_product(
    *,
    product_id: str,
    shop_id: str,
    media_service: MediaService,
) -> list[DocumentIR]:
    """拉取商品关联文档并解析为 DocumentIR（``source_kind=media_document``）。

    经 media 数据提供接口（list_documents_by_product + get_file_stream），
    ai 域**不** import media ORM/repository（跨域纪律）。
    店级隔离由调用方（catalog 已上架商品列表）保证——media 无 shop_id（ADR-011 §6）。
    解析失败/空文本的 document 跳过（``parse_document`` 返回空串），
    跳过统计由 reindex 调用方（Task 7）汇总到 ``ReindexStats``。
    """
    documents = await media_service.list_documents_by_product(product_id)

    irds: list[DocumentIR] = []
    for document in documents:
        data, _ = await media_service.get_file_stream(document.asset_id)
        text = parse_document(document.content_type, data)
        if not text:
            continue
        irds.append(
            DocumentIR(
                document_id=document.asset_id,  # media_document: document_id=附件 UUID
                shop_id=shop_id,
                product_id=product_id,
                source_kind="media_document",
                content_text=text,
                meta={},
            )
        )
    return irds
