"""ai 域跨店 ACL 检索 integration 测试（TDD 红阶段：app.ai.rag.retrieval 未实现）。

覆盖 spec ai-rag-retrieval「Shop-scoped vector retrieval ACL」：
- 两店各 reindex 双源后，shop A query 不返回 shop B 的 chunk（SQL 层 shop_id 过滤）

reindex 契约：reindex_shop(shop_id: str, *, db_session: AsyncSession) -> ReindexStats
retrieve 契约：retrieve_chunks(shop_id: str, query: str, top_k: int = 5) -> list[RetrievedChunk]
（design D13）
"""

import allure
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.service import MediaService
from tests.testkit.builders import unique_shop_name
from tests.testkit.db.catalog import seed_product, seed_shop
from tests.testkit.db.user import seed_active_user


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("retrieval")
@allure.title("retrieve_chunks 不跨店泄露：shop A query 不含 shop B 内容")
async def test_retrieve_chunks_acl_no_cross_shop_leak(
    db_session: AsyncSession,
    clean_ai_chunks: None,
    media_service: MediaService,
) -> None:
    """两店各 reindex 后，对 shop A 检索返回行的 shop_id 全为 A，且不含 shop B 的 product/content。"""
    from app.ai.rag.indexing.service import reindex_shop
    from app.ai.rag.retrieval.service import retrieve_chunks

    shop_a = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("acl-a"),
    )
    shop_b = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("acl-b"),
    )
    product_a = await seed_product(
        db_session, shop_id=shop_a, name="店铺A独有商品", is_published=True
    )
    await seed_product(
        db_session, shop_id=shop_b, name="店铺B独有商品", is_published=True
    )

    await reindex_shop(
        shop_id=shop_a, db_session=db_session, media_service=media_service
    )
    await reindex_shop(
        shop_id=shop_b, db_session=db_session, media_service=media_service
    )

    chunks = await retrieve_chunks(shop_id=shop_a, query="店铺", top_k=20)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.shop_id == shop_a
        assert chunk.product_id == product_a
        assert "店铺B独有" not in chunk.content_text
