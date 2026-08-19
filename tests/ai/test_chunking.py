"""ai 域 chunking 策略单元测试（TDD 红阶段：app.ai.rag 未实现）。

覆盖 spec ai-rag-indexing「Chunking by source kind」：
- catalog_text：短文本单 chunk（含 name+description、不含价格）、长文本多 chunk（首 chunk 含 name 前缀）、空 description
- media_document：段落切分、超长硬切

未来模块在函数内 lazy import，保持 collection 成功（红 = 运行期 ImportError）。
"""

import uuid

import allure

_DOC_MAX_REF = 800  # 与 RAG_CHUNK_MAX_CHARS 默认值对齐（design D6）


def _catalog_document(name: str, description: str = "") -> object:
    """构造 catalog_text 源 DocumentIR（红阶段 helper，未来 schema 落地后启用类型标注）。"""
    from app.ai.rag.schemas import DocumentIR

    product_id = str(uuid.uuid4())
    content = f"{name}\n{description}" if description else name
    return DocumentIR(
        document_id=product_id,  # catalog_text: document_id = product_id
        shop_id=str(uuid.uuid4()),
        product_id=product_id,
        source_kind="catalog_text",
        content_text=content,
        meta={},
    )


def _media_document(text: str) -> object:
    """构造 media_document 源 DocumentIR。"""
    from app.ai.rag.schemas import DocumentIR

    return DocumentIR(
        document_id=str(uuid.uuid4()),  # media_document: document_id = 附件 UUID
        shop_id=str(uuid.uuid4()),
        product_id=str(uuid.uuid4()),
        source_kind="media_document",
        content_text=text,
        meta={},
    )


def _split(document: object) -> list:
    """调用 split_document_to_chunks。"""
    from app.ai.rag.chunking import split_document_to_chunks

    return split_document_to_chunks(document)


@allure.epic("ai")
@allure.feature("chunking")
@allure.title("catalog 短文本 → 恰好 1 chunk，index=0，含 name+description 不含价格")
def test_catalog_short_text_single_chunk() -> None:
    """catalog 短文本：name+description 合并后 ≤ 800 → 单 chunk，content 含商品名与描述。"""
    chunks = _split(
        _catalog_document(
            name="红测试商品", description="这是一段商品描述，用于验证单 chunk 行为。"
        )
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "红测试商品" in chunks[0].content_text
    assert "这是一段商品描述" in chunks[0].content_text
    # price 是元数据，SHALL NOT 进入 chunk 文本（spec：content_text SHALL NOT 含价格）
    assert "99.00" not in chunks[0].content_text


@allure.epic("ai")
@allure.feature("chunking")
@allure.title("catalog 长文本 → 多 chunk，index 连续 0..n-1，首 chunk 含 name 前缀")
def test_catalog_long_text_multiple_chunks() -> None:
    """catalog 长文本：description 超过 800 → 多 chunk，首 chunk 含商品名前缀。"""
    long_description = "段落" * (_DOC_MAX_REF + 50)  # 远超单 chunk 上限
    chunks = _split(_catalog_document(name="红测试商品", description=long_description))

    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert "红测试商品" in chunks[0].content_text


@allure.epic("ai")
@allure.feature("chunking")
@allure.title("catalog 空 description → 仍产出 1 chunk（仅 name）")
def test_catalog_empty_description_still_chunks() -> None:
    """catalog 空 description：name 兜底，仍产出 chunk，content 含商品名。"""
    chunks = _split(_catalog_document(name="仅名字商品"))

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert "仅名字商品" in chunks[0].content_text


@allure.epic("ai")
@allure.feature("chunking")
@allure.title("media 文档按段落切分，index 连续 0..n-1")
def test_media_document_split_by_paragraph() -> None:
    """media 文档多段落 → 按段落切分为多 chunk，index 连续。"""
    text = "\n\n".join(f"第{i}段内容" for i in range(1, 6))
    chunks = _split(_media_document(text))

    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.content_text for c in chunks)


@allure.epic("ai")
@allure.feature("chunking")
@allure.title("media 超长单段落 → 硬切为多 chunk，不丢失内容")
def test_media_oversized_paragraph_hard_split() -> None:
    """media 超长单段落（无 \n\n）→ 硬切为多 chunk，index 连续。"""
    long_paragraph = "无分隔长内容" * (_DOC_MAX_REF + 30)
    chunks = _split(_media_document(long_paragraph))

    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
