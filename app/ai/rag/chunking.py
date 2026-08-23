"""ai 域 chunking：按 source_kind 路由的纯函数（DocumentIR → ProductChunkDraft[]）。

两策略（design D6）：
- ``catalog_text``：短文本单 chunk；超 ``RAG_CHUNK_MAX_CHARS`` 硬切（首 chunk 含 name——
  因 name 在 content_text 开头，spec「首个 chunk SHALL 含商品名前缀」）。
- ``media_document``：按段落（``\\n\\n``）切分；空段落丢弃；超长单段硬切。
"""

from app.ai.rag.schemas import (
    SOURCE_KIND_MEDIA_DOCUMENT,
    DocumentIR,
    ProductChunkDraft,
)
from app.infra.config import get_settings


def split_document_to_chunks(
    document: DocumentIR,
    *,
    max_chars: int | None = None,
) -> list[ProductChunkDraft]:
    """将 DocumentIR 转为有序 chunk 列表（``chunk_index`` 从 0 递增）。

    Args:
        max_chars: 单 chunk 最大字符数；None 时读 ``Settings.rag_chunk_max_chars``（默认 800）。
    """
    limit = max_chars if max_chars is not None else get_settings().rag_chunk_max_chars
    if document.source_kind == SOURCE_KIND_MEDIA_DOCUMENT:
        texts = _chunk_media(document.content_text, limit)
    else:
        texts = _chunk_catalog(document.content_text, limit)

    return [
        ProductChunkDraft(
            shop_id=document.shop_id,
            product_id=document.product_id,
            document_id=document.document_id,
            source_kind=document.source_kind,
            chunk_index=index,
            content_text=text,
        )
        for index, text in enumerate(texts)
    ]


def _chunk_catalog(content: str, max_chars: int) -> list[str]:
    """catalog_text：短文本单 chunk；超限硬切（首 chunk 含 name——name 在 content 开头）。"""
    if len(content) <= max_chars:
        return [content]
    return _hard_split(content, max_chars)


def _chunk_media(content: str, max_chars: int) -> list[str]:
    """media_document：按段落（\\n\\n）切分；空段落丢弃；超长单段硬切。"""
    chunks: list[str] = []
    for paragraph in content.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
        else:
            chunks.extend(_hard_split(paragraph, max_chars))
    return chunks


def _hard_split(text: str, max_chars: int) -> list[str]:
    """按 max_chars 硬切（保持顺序；str 切片按字符，不切坏多字节 UTF-8）。"""
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
