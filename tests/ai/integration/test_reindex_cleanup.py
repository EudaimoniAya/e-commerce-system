"""ai 域下架商品 reindex 清理 integration 测试（TDD 红阶段：indexing 未实现）。

覆盖 spec ai-rag-indexing「Index only published products with valid sources / Chunk cleanup」：
- 商品下架（is_published=false）后 reindex → PG SHALL NOT 含该 product_id 的任何 chunk
"""

import allure
import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.media.service import MediaService
from tests.testkit.builders import unique_shop_name
from tests.testkit.db.catalog import seed_product, seed_shop
from tests.testkit.db.user import seed_active_user


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("ai")
@allure.feature("indexing")
@allure.title("下架商品 reindex 后 PG 无该商品 chunk")
async def test_reindex_after_unpublish_clears_chunks(
    db_session: AsyncSession,
    ai_database_url: str,
    clean_ai_chunks: None,
    media_service: MediaService,
) -> None:
    """先 reindex 上架商品写入 chunk，模拟下架（is_published=false）后 reindex → chunk 被清除。"""
    from app.ai.rag.indexing.service import reindex_product

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("ai-cleanup"),
    )
    product_id = await seed_product(
        db_session, shop_id=shop_id, name="即将下架商品", is_published=True
    )

    await reindex_product(
        product_id=product_id,
        db_session=db_session,
        media_service=media_service,
    )

    # 模拟商家下架：PATCH is_published=false（项目无 DELETE /products，见 catalog-products spec）
    from app.catalog.models import Product

    await db_session.execute(
        update(Product).where(Product.id == product_id).values(is_published=False)
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
                "WHERE product_id = :product_id"
            ),
            {"product_id": product_id},
        )
    await engine.dispose()
    assert count == 0
