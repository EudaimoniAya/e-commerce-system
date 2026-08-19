"""catalog 域 RAG 索引语料只读 DTO integration 测试（TDD 红阶段：ProductRagSource 未实现）。

覆盖 spec catalog-products「Product RAG source read service」：
- 仅返回已上架商品；按 shop_id 过滤；全平台（shop_id=None）返回所有已上架
- ProductRagSource 字段契约：product_id / shop_id / name / description / price / is_published

调用契约（红阶段定义，绿阶段按此落地）：
    list_products_for_rag_indexing(shop_id: str | None, *, session: AsyncSession)
        -> list[ProductRagSource]
- ``session`` 为 MySQL 业务 session 注入（对齐 reindex 共享 SAVEPOINT 事务模式）。
"""

import allure
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.testkit.builders import unique_shop_name
from tests.testkit.db.catalog import seed_product, seed_shop
from tests.testkit.db.user import seed_active_user


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("rag_source")
@allure.title("list_products_for_rag_indexing 仅返回指定店已上架商品")
async def test_list_products_for_rag_indexing_filters_published_and_shop(
    db_session: AsyncSession,
) -> None:
    """shop_id=A 时仅返回 A 店已上架商品，不含未上架与其它店。"""
    from app.catalog.product_service import list_products_for_rag_indexing

    shop_a = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("rag-a"),
    )
    shop_b = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("rag-b"),
    )
    pub_a = await seed_product(
        db_session, shop_id=shop_a, name="A店已上架", is_published=True
    )
    unpub_a = await seed_product(
        db_session, shop_id=shop_a, name="A店未上架", is_published=False
    )
    pub_b = await seed_product(
        db_session, shop_id=shop_b, name="B店已上架", is_published=True
    )

    items = await list_products_for_rag_indexing(shop_id=shop_a, session=db_session)

    returned_ids = {item.product_id for item in items}
    assert pub_a in returned_ids
    assert unpub_a not in returned_ids
    assert pub_b not in returned_ids
    assert all(item.is_published is True for item in items)

    # 字段契约（spec：price 两位小数字符串，仅元数据）
    first = next(item for item in items if item.product_id == pub_a)
    assert first.shop_id == shop_a
    assert first.name == "A店已上架"
    assert first.price == "99.00"


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("rag_source")
@allure.title("list_products_for_rag_indexing(shop_id=None) 返回全平台已上架商品")
async def test_list_products_for_rag_indexing_all_platform(
    db_session: AsyncSession,
) -> None:
    """shop_id=None（运维全平台 reindex）返回所有已上架商品。"""
    from app.catalog.product_service import list_products_for_rag_indexing

    shop_a = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("all-a"),
    )
    shop_b = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("all-b"),
    )
    pub_a = await seed_product(
        db_session, shop_id=shop_a, name="A店已上架", is_published=True
    )
    unpub_a = await seed_product(
        db_session, shop_id=shop_a, name="A店未上架", is_published=False
    )
    pub_b = await seed_product(
        db_session, shop_id=shop_b, name="B店已上架", is_published=True
    )

    items = await list_products_for_rag_indexing(shop_id=None, session=db_session)

    returned_ids = {item.product_id for item in items}
    assert pub_a in returned_ids
    assert pub_b in returned_ids
    assert unpub_a not in returned_ids
