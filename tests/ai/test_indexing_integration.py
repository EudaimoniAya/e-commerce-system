"""ai 域 reindex 写入 PG integration 测试（TDD 红阶段：app.ai.rag.indexing 未实现）。

覆盖 spec ai-rag-indexing「Index only published products with valid sources」：
- 已上架商品 reindex → PG product_embedding_chunks 至少一行 chunk（catalog_text 源即可成立）

reindex 契约（红阶段定义，绿阶段实现按此落地）：
    reindex_product(product_id: str, *, db_session: AsyncSession, media_service) -> ReindexStats
- ``db_session`` 为 MySQL 业务 session 注入：reindex 经 catalog 数据提供接口读取商品，
  与测试共享同一 SAVEPOINT 事务（对齐项目「跨域共享 DB 事务」模式）；PG 侧经全局 AI session 真实写入。
"""

import allure
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.media.service import MediaService
from tests.testkit.builders import unique_shop_name
from tests.testkit.db.catalog import seed_product, seed_shop
from tests.testkit.db.user import seed_active_user


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("indexing")
@allure.title("reindex 已上架商品后 PG 存在该商品 chunk")
async def test_reindex_published_product_writes_chunks(
    db_session: AsyncSession,
    ai_database_url: str,
    clean_ai_chunks: None,
    media_service: MediaService,
) -> None:
    """已上架商品 reindex 后 PG product_embedding_chunks 含该 (shop_id, product_id) 至少一行。"""
    from app.ai.rag.indexing.service import reindex_product

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("ai-index"),
    )
    product_id = await seed_product(
        db_session, shop_id=shop_id, name="红阶段上架商品", is_published=True
    )

    await reindex_product(
        product_id=product_id,
        db_session=db_session,
        media_service=media_service,
    )

    engine = create_async_engine(ai_database_url)
    async with engine.connect() as conn:
        count = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM product_embedding_chunks "
                "WHERE shop_id = :shop_id AND product_id = :product_id"
            ),
            {"shop_id": shop_id, "product_id": product_id},
        )
    await engine.dispose()
    assert count >= 1
