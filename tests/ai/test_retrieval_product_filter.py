"""检索按会话范围过滤 integration 测试（TDD 红：product_id 参数尚未实现）。

覆盖 spec ai-rag-retrieval「Conversation-scoped product filter」：
- 传入 product_id=A 时不含同店商品 B
- 省略 product_id 仍可返回同店多商品
"""

import inspect
from unittest.mock import AsyncMock

import allure
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.builders import unique_shop_name
from tests.testkit.db.catalog import seed_product, seed_shop
from tests.testkit.db.user import seed_active_user


@allure.epic("ai")
@allure.feature("retrieval")
@allure.title("retrieve_chunks 签名含可选 product_id")
def test_retrieve_chunks_accepts_product_id() -> None:
    """查询契约：retrieve_chunks(..., product_id: str | None = None)。"""
    from app.ai.rag.retrieval.service import retrieve_chunks

    params = inspect.signature(retrieve_chunks).parameters
    assert "product_id" in params
    assert params["product_id"].default is None


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("retrieval")
@allure.title("传入 product_id 时不含同店其他商品")
async def test_retrieve_chunks_filters_by_product_id(
    db_session: AsyncSession,
    clean_ai_chunks: None,
    stub_media_service: AsyncMock,
) -> None:
    """同店 A/B 各有 chunk 时，product_id=A 的检索行全为 A，不含 B 文案。"""
    from app.ai.rag.indexing.service import reindex_shop
    from app.ai.rag.retrieval.service import retrieve_chunks

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("flt"),
    )
    product_a = await seed_product(
        db_session, shop_id=shop_id, name="过滤商品A独有", is_published=True
    )
    await seed_product(
        db_session, shop_id=shop_id, name="过滤商品B独有", is_published=True
    )

    await reindex_shop(
        shop_id=shop_id,
        db_session=db_session,
        media_service=stub_media_service,
    )

    chunks = await retrieve_chunks(
        shop_id=shop_id,
        query="过滤商品",
        top_k=20,
        product_id=product_a,
    )

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.shop_id == shop_id
        assert chunk.product_id == product_a
        assert "过滤商品B" not in chunk.content_text


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("retrieval")
@allure.title("省略 product_id 仍可返回同店多商品")
async def test_retrieve_chunks_without_product_id_returns_multiple(
    db_session: AsyncSession,
    clean_ai_chunks: None,
    stub_media_service: AsyncMock,
) -> None:
    """未传 product_id 时按店过滤，结果可含多个 product_id。"""
    from app.ai.rag.indexing.service import reindex_shop
    from app.ai.rag.retrieval.service import retrieve_chunks

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("allp"),
    )
    product_a = await seed_product(
        db_session, shop_id=shop_id, name="过滤商品A独有", is_published=True
    )
    product_b = await seed_product(
        db_session, shop_id=shop_id, name="过滤商品B独有", is_published=True
    )

    await reindex_shop(
        shop_id=shop_id,
        db_session=db_session,
        media_service=stub_media_service,
    )

    chunks = await retrieve_chunks(shop_id=shop_id, query="过滤商品", top_k=20)

    returned_ids = {chunk.product_id for chunk in chunks}
    assert product_a in returned_ids
    assert product_b in returned_ids
    assert all(chunk.shop_id == shop_id for chunk in chunks)
