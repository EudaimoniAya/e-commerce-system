"""catalog 域 RAG 索引语料只读 DTO integration 测试（TDD 红阶段：ProductRagSource 未实现）。

覆盖 spec catalog-products「Product RAG source read service」：
- 仅返回已上架商品；按 shop_id 过滤；全平台（shop_id=None）返回所有已上架
- ProductRagSource 字段：product_id / shop_id / name / description / is_published（无 price）
- get_product_for_rag_indexing：上架返回源；下架或不存在返回 None

调用契约：
    list_products_for_rag_indexing(shop_id: str | None, *, session: AsyncSession)
        -> list[ProductRagSource]
    get_product_for_rag_indexing(product_id: str, *, session: AsyncSession)
        -> ProductRagSource | None
"""

import uuid

import allure
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.schemas import ProductRagSource
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

    first = next(item for item in items if item.product_id == pub_a)
    assert first.shop_id == shop_a
    assert first.name == "A店已上架"
    assert "price" not in ProductRagSource.model_fields
    assert not hasattr(first, "price")


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


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("rag_source")
@allure.title("get_product_for_rag_indexing 上架商品返回语料源")
async def test_get_product_for_rag_indexing_published(
    db_session: AsyncSession,
) -> None:
    """已上架商品按 id 返回 ProductRagSource，字段与 list 项一致。"""
    from app.catalog.product_service import get_product_for_rag_indexing

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("get-pub"),
    )
    product_id = await seed_product(
        db_session,
        shop_id=shop_id,
        name="单商品上架",
        is_published=True,
    )

    source = await get_product_for_rag_indexing(product_id, session=db_session)

    assert source is not None
    assert source.product_id == product_id
    assert source.shop_id == shop_id
    assert source.name == "单商品上架"
    assert source.is_published is True
    assert "price" not in ProductRagSource.model_fields


@pytest.mark.integration
@pytest.mark.asyncio
@allure.epic("catalog")
@allure.feature("rag_source")
@allure.title("get_product_for_rag_indexing 下架或不存在返回 None")
async def test_get_product_for_rag_indexing_unpublished_or_missing(
    db_session: AsyncSession,
) -> None:
    """未上架与不存在的 id 均返回 None，不抛 HTTP 错误。"""
    from app.catalog.product_service import get_product_for_rag_indexing

    shop_id = await seed_shop(
        db_session,
        owner_user_id=await seed_active_user(db_session),
        name=unique_shop_name("get-miss"),
    )
    unpublished_id = await seed_product(
        db_session,
        shop_id=shop_id,
        name="单商品下架",
        is_published=False,
    )

    unpublished = await get_product_for_rag_indexing(
        unpublished_id, session=db_session
    )
    missing = await get_product_for_rag_indexing(
        str(uuid.uuid4()), session=db_session
    )

    assert unpublished is None
    assert missing is None
